This is a fork from [Stanford Compression Library](https://github.com/kedartatwawadi/stanford_compression_library) for Nan's LZ78 implementation project. 
# LZ78 Compression Algorithm

## Introduction

We have discussed the LZ77 compression algorithm and its practical realization in depth during our class. LZ77 employs sliding windows (or buffer) to avoid searching too far back in the input. This approach, albeit effective, makes the selection of the buffer size critical. A smaller buffer results in reduced compression time but demands more space. Conversely, a larger buffer size reduces required space but prolongs the compression time. Consequently, the parameters of LZ77 need to be optimized according to the pattern of the input data.

Since there are several universal compressors with similar features and performance, I have chosen to examine another form of dictionary-based compression also developed by Ziv and Lempel - LZ78. The LZ78 algorithms, named after its inventors Abraham Lempel and Jacob Ziv with the '78' denoting its year of publication in 1978. It is a lossless data compression algorithm that forms the basis for several ubiquitous formats, including GIF and TIFF. The primary motivation for developing LZ78 was to create a universal compression algorithm that does not require any prior knowledge of the input and choosing of the buffer size, addressing an inherent drawback of LZ77.  

## Literature/Code Review

Unlike LZ77, which defines a dictionary of phrases through a fixed-length window of text previously seen, LZ78 allows the dictionary to be a potentially limitless set of previously observed phrases. LZ78 identifies and adds phrases to a dictionary. When a phrase reoccurs, LZ78 outputs a dictionary index token instead of repeating the phrase, along with one character that follows that phrase. The new phrase (the reoccurred phrase plus the character that follows) will be added to the dictionary as a new phrase. The dictionary will be represented as a n-ary tree where n is the number of tokens used to form token sequences, and each leave will be a phrase.

$Example$: encode **"EE274 cool cool"**

|index  |output |string |
|-------|-------|-------|
|1      |(0,A)  |E      |
|2      |(1,2)  |E2     |
|3      |(0,7)  |7      |
|4      |(0,4)  |4      |
|5      |(0, )  |' '    |
|6      |(0,c)  |c      |
|7      |(0,o)  |o      |
|8      |(7,l)  |ol     |
|9      |(5,c)  |' c'   |
|10     |(7,o)  |co     |
|11     |(8,)   |ol     |

```
def lz78_compress(data):
    dictionary = {}
    result = []
    pos = 0
    while pos < len(data):
        prefix = data[pos]
        advance = 1
        while prefix + data[pos + advance] in dictionary:
            prefix += data[pos + advance]
            advance++
        result += (dictionary[prefix], data[pos + advance])
        dictionary[prefix + data[pos + advance]] = len(dictionary)
        pos = pos + advance
    return result
```

#### Reference:
- [Stanford EE376C notes on Lempel-Ziv compression](https://web.stanford.edu/class/ee376a/files/EE376C_lecture_LZ.pdf)
- [LZ78 on Wikipedia](https://en.wikipedia.org/wiki/LZ77_and_LZ78#LZ78)
- [Data Compression APplets Library](http://www.stringology.org/DataCompression/index_en.html)

## Methods

The aim is to build a Python implementation of the LZ78 algorithm, with a focus on clarity and performance. Key features to implement include:
Creating a dictionary trie for encoding efficiency.
Output encoding including variable-length bit support.
Decoding functionality that reconstructs the original data from compressed content.

I expect to achieve an implementation that can compress and decompress data files at similar or better speed and efficiency compared to LZ77. Evaluation will take place both qualitatively, through code reviews and ensuring the implementation adheres closely to the original specification, and quantitatively, through benchmarks on compression ratio and speed, comparing these with the SCL implementation of LZ77.

I will also explore the effects of having an initialization dictionary, versus starting with an empty dictionary. I expect having an initialized dictionary containing common substrings pertinent to the data being compressed can improve the compression ratio. However, this does require having prior knowledge about the nature of the data.

# Progress report
## Completed Work
## Planned Work for Remaining Weeks
