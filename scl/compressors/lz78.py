import argparse
from typing import List, Tuple
from scl.core.data_encoder_decoder import DataDecoder, DataEncoder
from scl.core.data_block import DataBlock
from scl.utils.bitarray_utils import BitArray
from scl.core.encoded_stream import EncodedBlockWriter, EncodedBlockReader
from scl.core.data_stream import Uint8FileDataStream, TextFileDataStream
from lz77 import EmpiricalIntHuffmanDecoder, EmpiricalIntHuffmanEncoder, LogScaleBinnedIntegerDecoder, LogScaleBinnedIntegerEncoder
from scl.utils.test_utils import (
    try_lossless_compression,
)

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
        dict_index = 1
        input_data = data_block.data_list
        input_size = len(input_data)
        start = 0

        for end in range(1, input_size+1):
            new_string = tuple(input_data[start:end])
            # If the prefix string + current character is not in the dictionary, add
            # (index of the prefix, current character) tuple to the output and the dictionary
            if new_string not in dictionary:
                prefix = tuple(input_data[start:end-1])
                output.append((dictionary.get(prefix, 0), input_data[end-1]))
                dictionary[new_string] = dict_index
                dict_index += 1
                start = end
            # Else if prefix string + current character is in the dictionary, advance to the next character.
        
        # Handle edge case when the last part of the input is in the dictionary
        if start != input_size:
            output.append((dictionary[tuple(input_data[start:input_size])], None))

        return output, dictionary
                
    def encode_indexes(self, indexes: List):
        log_scale_binned_coder = LogScaleBinnedIntegerEncoder(
            offset=self.log_scale_binned_coder_offset
        )
        return log_scale_binned_coder.encode_block(
            DataBlock(indexes)
        )
        
    def encode_literals(self, literals: List):
        """Perform entropy encoding of the literals and return the encoded bitarray.

        Encode literals with empirical Huffman code.

        Args:
            encoded_bitarray (BitArray): encoded bit array
        """
        encoded_bitarray = EmpiricalIntHuffmanEncoder(alphabet_size=256).encode_block(
            DataBlock(literals)
        )
        return encoded_bitarray
        
    def encode_tuples(self, tuples: Tuple):
        encoded_indexes = self.encode_indexes([index for index, _ in tuples])
        # If the last tuple has empty string
        _, last_literal = tuples[-1]
        if last_literal is None:
            encoded_literals = self.encode_literals([lit for _, lit in tuples[:-1]])
        else:
            encoded_literals = self.encode_literals([lit for _, lit in tuples])
        return encoded_indexes + encoded_literals
    
    def encode_block(self, data_block: DataBlock):
        # first do lz77 parsing
        lz78_tuples, dictionary = self.lz78_parse_and_generate_dict(data_block)
        # now encode sequences and literals
        encoded_bitarray = self.encode_tuples(lz78_tuples)
        return encoded_bitarray

    def encode_file(self, input_file_path: str, encoded_file_path: str, block_size: int = 10000):
        """utility wrapper around the encode function using Uint8FileDataStream

        Args:
            input_file_path (str): path of the input file
            encoded_file_path (str): path of the encoded binary file
            block_size (int): choose the block size to be used to call the encode function
        """
        # call the encode function and write to the binary file
        with Uint8FileDataStream(input_file_path, "rb") as fds:
            with EncodedBlockWriter(encoded_file_path) as writer:
                self.encode(fds, block_size=block_size, encode_writer=writer)


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
            if symbol is None: # last tuple could have None symbol as the last part of the input is in the dicitonary
                output.extend(dictionary[index])
                return output

            new_string = tuple([symbol])
            if index != 0:
                new_string = dictionary[index] + new_string

            dictionary[dict_index] = new_string
            dict_index += 1
            output.extend(new_string)
        return output

    def decode_indexes(self, encoded_bitarray: BitArray):
        log_scale_binned_coder = LogScaleBinnedIntegerDecoder(
            offset=self.log_scale_binned_coder_offset
        )
        indexes, num_bits_consumed = log_scale_binned_coder.decode_block(encoded_bitarray)
        return indexes.data_list, num_bits_consumed
            
    def decode_literals(self, encoded_bitarray: BitArray):
        """Perform entropy decoding of the literals and return the literals
        and the number of bits consumed.

        Args:
            encoded_bitarray (BitArray): encoded bit array
        """
        literals, num_bits_consumed = EmpiricalIntHuffmanDecoder(alphabet_size=256).decode_block(
            encoded_bitarray
        )
        return [l for l in literals.data_list], num_bits_consumed
    
    def decode_block(self, encoded_bitarray: BitArray):
        indexes, num_bits_consumed_sequences = self.decode_indexes(encoded_bitarray)
        encoded_bitarray = encoded_bitarray[num_bits_consumed_sequences:]
        literals, num_bits_consumed_literals = self.decode_literals(encoded_bitarray)
        num_bits_consumed = num_bits_consumed_sequences + num_bits_consumed_literals

        # If the last tuple had empty symbol, then literals will have one less item than indexes
        if len(literals) + 1 == len(indexes):
            literals.append(None)
        else:
            assert len(literals) == len(indexes)
        encoded_tuples = [(z[0], z[1]) for z in zip(indexes, literals)]
        decoded_list = self.lz78_decode_from_tuples(encoded_tuples)

        return DataBlock(decoded_list), num_bits_consumed

    def decode_file(self, encoded_file_path: str, output_file_path: str):
        """utility wrapper around the decode function using Uint8FileDataStream

        Args:
            encoded_file_path (str): input binary file
            output_file_path (str): output (text) file to which decoded data is written
        """

        # decode data and write output to a text file
        with EncodedBlockReader(encoded_file_path) as reader:
            with Uint8FileDataStream(output_file_path, "wb") as fds:
                self.decode(reader, fds)


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
        ("E",): 1,
        ("E", "2"): 2,
        ("7",): 3,
        ("4",): 4,
        (" ",): 5,
        ("c",): 6,
        ("o",): 7,
        ("o", "l"): 8,
        (" ", "c"): 9,
        ("o", "o"): 10,
        ("l",): 11,
    }
    output, dict = encoder.lz78_parse_and_generate_dict(data_block)

    assert output == expected_output
    assert dict == expected_dict

def test_lz78_encode_to_dict_end_matched():
    """
    Test that lz78 produces expected dictionary and expected list of tuples.
    """
    encoder = LZ78Encoder()

    input_string = "EE274 cool co"
    data_list = [*input_string]
    data_block = DataBlock(data_list)

    expected_output = [(0,"E"), (1,"2"), (0,"7"), (0,"4"), (0," "), (0,"c"),
                       (0,"o"), (7,"l"), (5,"c"), (7,None)]
    expected_dict = {
        ("E",): 1,
        ("E", "2"): 2,
        ("7",): 3,
        ("4",): 4,
        (" ",): 5,
        ("c",): 6,
        ("o",): 7,
        ("o", "l"): 8,
        (" ", "c"): 9,
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
    decoded_list = decoder.lz78_decode_from_tuples(input_tuples)

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
    decoded_list = decoder.lz78_decode_from_tuples(encoded_tuples)

    assert decoded_list == data_list

def test_lz78_encode_decode_e2e():
    """
    Test that lz78 produces expected original input string.
    """
    encoder = LZ78Encoder()
    decoder = LZ78Decoder()

    input_string = b"EE274 cool cool"
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
    BLOCKSIZE = 100_000  # encode in 100 KB blocks

    args = parser.parse_args()

    if args.decompress:
        decoder = LZ78Decoder()
        decoder.decode_file(args.input, args.output)
    else:
        encoder = LZ78Encoder()
        encoder.encode_file(args.input, args.output, block_size=BLOCKSIZE)
