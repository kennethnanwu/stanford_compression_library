"""
LZ78 works by identifing and adding past phrases to a dictionary. When a phrase reoccurs,
LZ78 outputs a dictionary index token of that phrase instead of repeating the phrase,
along with one character that follows that phrase. The new phrase (the reoccurred phrase
plus the character that follows) will be added to the dictionary as a new phrase. 
The dictionary index and the following character form a tuple, and the tuple is added
to a list. The output of a LZ78 compression will be this list of tuples.
These tuples are then entropy coded. LZ77 forms the basis of popular compressors like GIF.

The encoder and decoder have 1 parameter:
- initial_dic: Initialization dictionary to use for encoding and decoding to potentially
speed up the "initialization" of the dictionary. That is, the initialization dictionary
should contains common phrases and words of the input. This should help increase
the compression ratio by representing the first first few commonly seen words/phrases
with dictionary indexes.

The algorithm:

- keep a dictionary that stores a map from previousely seen strings to its position in the output list.
- keep a list of tuples of the dictionary index of the previously seens phrase and the character
that follows. In case there is no match in the dictionary, using 0 as the index. This is the ouptut list.
- to find a match during parsing, we look up future substring in the input and then find the longest
match in the dictionary keys. The value of this key is the index of the substring in the output
list. The index and the following character forms a tuple which is then put into the output list.
We then append the folliwng character to this substring to form a new substring. This new substring
will be stored in the dictionary as a key, whose value will be the length of the output list.

Entropy encoding:
- Tuples are formed by (index, literal)
- Literals are treated as Unicode and converted to integer using Python's ord() function.
- Indexes and literals in Unicode integer format are then encoded by first binning the integer
  in log scale and then encoding with empirical Huffman coder, and the difference to 2^logarithm
  (residual) as plain old bits. See LogScaleBinnedIntegerEncoder for details.

Current limitations:
1. During compression we allow the dictionary to grow limitless. We could enforce
    a length on which the dictionary could not add more entries to limit the 
    memory usage.

Benchmarks on a few files from https://github.com/nemequ/squash-corpus and
https://corpus.canterbury.ac.nz/descriptions/#cantrbry (plus a few handmade).

All sizes are in bytes.

| File                                | raw size | scl-lz77 size    | wunan-lz78 size |
|-------------------------------------|----------|------------------|-----------------|
| alice29.txt                         |152089    |54106             |68850            |
| sherlock.txt                        |387870    |127092            |158910           |

"""
import argparse
from typing import List, Tuple
from scl.core.data_encoder_decoder import DataDecoder, DataEncoder
from scl.core.data_block import DataBlock
from scl.utils.bitarray_utils import BitArray
from scl.core.encoded_stream import EncodedBlockWriter, EncodedBlockReader
from scl.core.data_stream import AsciiFileDataStream
from lz77 import EmpiricalIntHuffmanDecoder, EmpiricalIntHuffmanEncoder, LogScaleBinnedIntegerDecoder, LogScaleBinnedIntegerEncoder
from scl.utils.test_utils import (
    create_random_binary_file,
    try_file_lossless_compression,
    try_lossless_compression,
)

_test_print_100 = 100
class LZ78Encoder(DataEncoder):
    def __init__(
        self,
        initial_dict: dict = None,
        log_scale_binned_coder_offset = 16,
    ):
        """LZ78Encoder. Encode data using LZ78 scheme.

        Args:
            initial_dict (dict, optional): initialize dictionary. The same initial dict should be used for the decoder.
            log_scale_binned_coder_offset (int): offset for log scale binned integer encoder

        """
        self.log_scale_binned_coder_offset = log_scale_binned_coder_offset
        self.dictionary = {}
        # if initial_dict is provided, update dictionary
        if initial_dict is not None:
            self.dictionary = initial_dict
    
    def lz78_parse_and_generate_dict(self, data_block: DataBlock):
        dictionary = self.dictionary
        output = []
        prefix = ""
        dict_index = 1
        input_data = data_block.data_list

        for symbol in input_data:
            new_string = prefix + symbol
            # If prefix string + current character is in the dictionary, advance to the next character.
            if new_string in dictionary:
                prefix = new_string
            # If the prefix string + current character is not in the dictionary, add
            # (index of the prefix, current character) tuple to the output and the dictionary
            else:
                output.append((dictionary.get(prefix, 0), symbol))
                dictionary[new_string] = dict_index
                dict_index += 1
                prefix = ""
        
        # Handle edge case when the last part of the input is in the dictionary
        if prefix:
            output.append((dictionary[prefix], ""))

        return output, dictionary
                
    def encode_indexes(self, indexes: List):
        log_scale_binned_coder = LogScaleBinnedIntegerEncoder()
        return log_scale_binned_coder.encode_block(
            DataBlock(indexes)
        )
        
    def encode_literals(self, literals: List):
        """Perform entropy encoding of the literals and return the encoded bitarray.

        Encode literals with empirical Huffman code.

        Args:
            encoded_bitarray (BitArray): encoded bit array
        """
        # If the last tuple has empty string, skip it. Because empty string cannot be encoded to a number.
        if not literals[-1]:
            literals = literals[:-1]
        # Convert to Unicode integer
        literals = [ord(l) for l in literals]
        log_scale_binned_coder = LogScaleBinnedIntegerEncoder(offset=self.log_scale_binned_coder_offset)
        encoded_bitarray = log_scale_binned_coder.encode_block(DataBlock(literals))

        # # Try using Huffman for ascii inputs
        # encoded_bitarray = EmpiricalIntHuffmanEncoder(alphabet_size=128).encode_block(DataBlock(literals))
        
        return encoded_bitarray
        
    def encode_tuples(self, tuples: Tuple):
        encoded_indexes = self.encode_indexes([index for index, _ in tuples])
        encoded_literals = self.encode_literals([lit for _, lit in tuples])
        return encoded_indexes + encoded_literals
    
    def encode_block(self, data_block: DataBlock):
        # first do lz78 parsing
        lz78_tuples, dictionary = self.lz78_parse_and_generate_dict(data_block)
        # now encode (index, literal) tuples
        encoded_bitarray = self.encode_tuples(lz78_tuples)
        return encoded_bitarray



class LZ78Decoder(DataDecoder):
    def __init__(
        self,
        initial_dict: dict = None,
        log_scale_binned_coder_offset = 16,
    ):
        """LZ78Decoder. Decode data using LZ78 scheme.

        Args:
            initial_dict (dict, optional): initialize dictionary. The same initial dict should be used for the encoder.
            log_scale_binned_coder_offset (int): offset for log scale binned integer encoder
        """
        self.log_scale_binned_coder_offset = log_scale_binned_coder_offset
        self.dictionary = {}
        # if initial_dict is provided, update dictionary
        if initial_dict is not None:
            for key, value in initial_dict:
                self.dictionary[value] = key
    
    def lz78_decode_from_tuples(self, encoded_tuples):
        """Decode tuples to original messages.
        
        Args:
            encoded_tuples: ordered list of tuples (index, symbol).
        """
        dictionary = self.dictionary
        output = []
        dict_index = 1
        
        for index, symbol in encoded_tuples:
            new_string = symbol
            if index != 0:
                new_string = dictionary[index] + symbol

            dictionary[dict_index] = new_string
            dict_index += 1
            output.append(new_string)
        decoded_input = ''.join(output)
        decoded_list = [*decoded_input]
        return decoded_input, decoded_list

    def decode_indexes(self, encoded_bitarray: BitArray):
        log_scale_binned_coder = LogScaleBinnedIntegerDecoder()
        indexes, num_bits_consumed = log_scale_binned_coder.decode_block(encoded_bitarray)
        return indexes.data_list, num_bits_consumed
            
    def decode_literals(self, encoded_bitarray: BitArray):
        """Perform entropy decoding of the literals and return the literals
        and the number of bits consumed.

        Args:
            encoded_bitarray (BitArray): encoded bit array
        """
        # Huffman for ASCII input
        # literals, num_bits_consumed = EmpiricalIntHuffmanDecoder(alphabet_size=128).decode_block(
        #     encoded_bitarray
        # )

        literals, num_bits_consumed = LogScaleBinnedIntegerDecoder(offset=self.log_scale_binned_coder_offset).decode_block(
            encoded_bitarray
        )
        # Convert from unicode interger back to symbol
        return [chr(l) for l in literals.data_list], num_bits_consumed
    
    def decode_block(self, encoded_bitarray: BitArray):
        indexes, num_bits_consumed_sequences = self.decode_indexes(encoded_bitarray)
        encoded_bitarray = encoded_bitarray[num_bits_consumed_sequences:]
        literals, num_bits_consumed_literals = self.decode_literals(encoded_bitarray)
        num_bits_consumed = num_bits_consumed_sequences + num_bits_consumed_literals

        # If the last tuple had empty symbol, then literals will have one less item than indexes
        if len(literals) + 1 == len(indexes):
            literals.append("")
        else:
            assert len(literals) == len(indexes)
        encoded_tuples = [(z[0], z[1]) for z in zip(indexes, literals)]
        _, decoded_list = self.lz78_decode_from_tuples(encoded_tuples)

        return DataBlock(decoded_list), num_bits_consumed



def test_lz78_encode_to_dict():
    """
    Test that lz78 produces expected dictionary and expected list of tuples.
    """
    encoder = LZ78Encoder()

    input_string = "EE274 cool cool"
    data_list = [*input_string]
    data_block = DataBlock(data_list)

    expected_output = [(0,"E"), (1,"2"), (0,"7"), (0,"4"), (0," "), (0,"c"), (0,"o"), (7,"l"), (5,"c"), (7,"o"), (0,"l")]
    expected_dict = {
        "E": 1,
        "E2":2,
        "7": 3,
        "4": 4,
        " ": 5,
        "c": 6,
        "o": 7,
        "ol":8,
        " c":9,
        "oo":10,
        "l": 11,
    }
    output, dict = encoder.lz78_parse_and_generate_dict(data_block)

    assert output == expected_output
    assert dict == expected_dict

def test_lz77_decode_from_dict():
    """
    Test that lz78 decodes from a list of tuples.
    """
    input = "EE274 cool cool"
    input_tuples = [(0,"E"), (1,"2"), (0,"7"), (0,"4"), (0," "), (0,"c"), (0,"o"), (7,"l"), (5,"c"), (7,"o"), (0,"l")]
    decoder = LZ78Decoder()
    decoded_input, decoded_list = decoder.lz78_decode_from_tuples(input_tuples)

    assert decoded_input == input
    assert decoded_list == [*input]

def test_lz78_encode_to_dict_then_decode():
    """
    Test that lz78 produces expected dictionary and expected list of tuples.
    """
    encoder = LZ78Encoder()
    decoder = LZ78Decoder()

    input_string = "EE274 cool cool"
    data_list = [*input_string]
    data_block = DataBlock(data_list)

    encoded_tuples, dict = encoder.lz78_parse_and_generate_dict(data_block)
    decoded_input, decoded_list = decoder.lz78_decode_from_tuples(encoded_tuples)

    assert decoded_input == input_string
    assert decoded_list == data_list

def test_lz78_encode_decode_e2e():
    """
    Test that lz78 produces expected original input string.
    """
    encoder = LZ78Encoder()
    decoder = LZ78Decoder()

    input_string = "EE274 cool cool"
    data_list = [*input_string]
    data_block = DataBlock(data_list)
    is_lossless, _, _ = try_lossless_compression(data_block, encoder, decoder)
    assert is_lossless


if __name__ == "__main__":
    # Provide a simple CLI interface below for convenient experimentation
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--decompress", help="decompress", action="store_true")
    parser.add_argument("-i", "--input", help="input file", required=True, type=str)
    parser.add_argument("-o", "--output", help="output file", required=True, type=str)

    # constants
    BLOCKSIZE = 400_000  # encode in 100 KB blocks

    args = parser.parse_args()

    if args.decompress:
        decoder = LZ78Decoder(
            log_scale_binned_coder_offset = 128,
        )
        decoder.decode_file(args.input, args.output)
    else:
        encoder = LZ78Encoder(
            log_scale_binned_coder_offset = 128,
        )
        encoder.encode_file(args.input, args.output, block_size=BLOCKSIZE)
