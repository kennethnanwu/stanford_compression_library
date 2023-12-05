import random
import string

# Specify the desired file size in bytes
file_size = 1048576  # 1 MB = 1048576 bytes

# Generate random characters
random_characters = ''.join(random.choice(string.ascii_letters) for _ in range(file_size))

# Write the random characters to a file
with open('random_characters.txt', 'w') as f:
    f.write(random_characters)