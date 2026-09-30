#!/usr/bin/env python3
# Script for Encoding/Decoding Twin-Hex cipher
# Source Website: https://www.calcresult.com/misc/cyphers/twin-hex.html

# Github: https://github.com/htr-tech/0xTwin
# HappyHacking

import argparse


class TwinHexEncoder:
    cbase = [chr(x) + chr(y) for x in range(32, 128) for y in range(32, 128)]
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"

    def base36encode(self, number):
        if not isinstance(number, (int)):
            raise TypeError("must be an integer")
        if number < 0:
            raise ValueError("must be positive")
        encoded_string = ""
        while number:
            number, i = divmod(number, 36)
            encoded_string = self.alphabet[i] + encoded_string
        return encoded_string or self.alphabet[0]

    def encrypt(self, char):
        flag_out = ""
        for i in range(0, len(char), 2):
            pair = char[i : i + 2]
            if len(pair) < 2:
                pair += " "
            try:
                index = self.cbase.index(pair)
            except ValueError:
                raise ValueError("only printable ASCII can be encoded") from None
            flag_out += self.base36encode(index).ljust(3, " ")
        return flag_out


class TwinHexDecoder:
    cbase = [chr(x) + chr(y) for x in range(32, 128) for y in range(32, 128)]

    def decrypt(self, char):
        # Raise rather than exit(): this runs inside the bot's receive thread
        try:
            triples = [char[i : i + 3] for i in range(0, len(char), 3)]
            return "".join(self.cbase[int(x, 36)] for x in triples if x.strip())
        except (ValueError, IndexError) as e:
            raise ValueError(f"invalid Twin-Hex input: {e}") from None


def main():
    print(
        """
    _______         ___________       .__        
    \   _  \ ___  __\__    ___/_  _  _|__| ____  
    /  /_\  \\\  \/  / |    |  \ \\/ \\/ /  |/    \\
    \  \_/   \>    <  |    |   \     /|  |   |  \\
     \_____  /__/\_ \ |____|    \/\_/ |__|___|  /
           \/      \/                         \/ 
          Twin-Hex Cipher Encoder/Decoder
    """
    )
    parser = argparse.ArgumentParser(
        description="Script for Encoding/Decoding Twin-Hex Cipher"
    )
    parser.add_argument("-d", "--decode", action="store_true", help="Decode Twin-Hex")
    parser.add_argument(
        "-e", "--encode", action="store_true", help="Encode to Twin-Hex"
    )
    parser.add_argument("text", nargs="?")
    args = parser.parse_args()

    if args.text:
        try:
            if args.decode:
                print(f"Decoded Flag: {TwinHexDecoder().decrypt(args.text)}")
            elif args.encode:
                print(f"Encoded Flag: {TwinHexEncoder().encrypt(args.text)}")
            else:
                exit("[!] Provide either --encode or --decode argument")
        except ValueError as e:
            exit(f"Error: {e}")
    else:
        exit("usage: twin_cipher.py [-h] [-d] [-e] [text]")


if __name__ == "__main__":
    main()
