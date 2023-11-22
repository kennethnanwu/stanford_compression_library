from scl.core.data_encoder_decoder import DataDecoder, DataEncoder
from scl.core.data_block import DataBlock

class LZ77Encoder(DataEncoder):
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
    
    def encode_block(self, data_block: DataBlock):
        # first do lz77 parsing
        lz77_sequences, literals = self.lz77_parse_and_generate_sequences(data_block)
        # now encode sequences and literals
        encoded_bitarray = self.streams_encoder.encode_block(lz77_sequences, literals)
        return encoded_bitarray

