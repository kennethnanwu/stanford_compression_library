import argparse
from scl.core.data_encoder_decoder import DataDecoder, DataEncoder
from scl.core.data_block import DataBlock

class LZ78Encoder(DataEncoder):
    def __init__(
        self,
        initial_dict: dict = None,
    ):
        """LZ78Encoder. Encode data using LZ78 scheme.

        Args:
            initial_dict (dict, optional): initialize dictionary. The same initial dict should be used for the decoder.

        """
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
                
    
    def encode_block(self, data_block: DataBlock):
        # first do lz77 parsing
        output, dictionary = self.lz78_parse_and_generate_dict(data_block)
        # now encode sequences and literals
        # encoded_bitarray = self.streams_encoder.encode_block(lz77_sequences, literals)
        return output


class LZ78Decoder(DataDecoder):
    def __init__(
        self,
        initial_dict: dict = None,
    ):
        """LZ78Decoder. Decode data using LZ78 scheme.

        Args:
            initial_dict (dict, optional): initialize dictionary. The same initial dict should be used for the encoder.

        """
        self.dictionary = {}

        # if initial_dict is provided, update dictionary
        if initial_dict is not None:
            self.dictionary = initial_dict


def test_lz77_sequence_generation():
    """
    Test that lz77 produces expected sequences
    Also test behavior across blocks both when we reset and when we don't
    """
    encoder = LZ78Encoder()

    data_list = [
        "E",
        "E",
        "2",
        "7",
        "4",
        " ",
        "c",
        "o",
        "o",
        "l",
        " ",
        "c",
        "o",
        "o",
        "l",
    ]
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


if __name__ == "__main__":
    # Provide a simple CLI interface below for convenient experimentation
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--decompress", help="decompress", action="store_true")
    parser.add_argument("-i", "--input", help="input file", required=True, type=str)
    parser.add_argument("-o", "--output", help="output file", required=True, type=str)
    parser.add_argument(
        "-w", "--window_init", help="initialize window from file (like zstd dictionary)", type=str
    )

    # constants
    BLOCKSIZE = 100_000  # encode in 100 KB blocks

    args = parser.parse_args()

    initial_window = None
    if args.window_init is not None:
        with open(args.window_init, "rb") as f:
            initial_window = list(f.read())

    if args.decompress:
        decoder = LZ78Decoder(initial_window=initial_window)
        decoder.decode_file(args.input, args.output)
    else:
        encoder = LZ78Encoder(initial_window=initial_window)
        encoder.encode_file(args.input, args.output, block_size=BLOCKSIZE)
