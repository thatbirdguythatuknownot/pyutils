import os
import math
import itertools
import struct
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from .xor import xor, decrypt_repeating_key_xor
from ..itertools2 import grouper

#utils
def round_to_multiple(x, y):
	return math.ceil(x / y) * y

def pad_pkcs7(s, block_size=16):
	length = round_to_multiple(len(s), block_size)
	pad_len = length - len(s)
	if pad_len == 0:
		pad_len = block_size
	return s + bytes((pad_len, ) * pad_len)

def unpad_pkcs7(s, block_size=16):
	pad_length = s[-1]
	padding = s[-pad_length:]
	if all(c == padding[0] for c in padding):
		return s[:-pad_length]
	else:
		raise ValueError(f"Invalid PKCS#7 padding on {s!r}")

#actual encryption/decryption funcs
def aes_ecb(s, key, mode, no_pad=False):
	cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
	if mode == "decrypt":
		func = cipher.decryptor()
	elif mode == "encrypt":
		if not no_pad:
			s = pad_pkcs7(s, 16)
		func = cipher.encryptor()
	else:
		raise ValueError(f"Illegal mode {mode} is not 'decrypt' or 'encrypt' ")
	return func.update(s) + func.finalize()

def aes_cbc(s, key, iv, mode):
	if mode == "encrypt":
		s = pad_pkcs7(s, 16)
	blocks = map(bytes, grouper(s, 16))
	full_transformed = b""
	prev = iv
	for block in blocks:
		if mode == "encrypt":
			transformed = aes_ecb(xor(block, prev), key, mode, no_pad=True)
			prev = transformed
			full_transformed += transformed
		else:
			transformed = aes_ecb(block, key, mode)
			full_transformed += xor(transformed, prev)
			prev = block
	return full_transformed

def aes_ctr_keystream(key, nonce):
	for counter in itertools.count():
		yield from aes_ecb(struct.pack("<QQ", nonce, counter), key, "encrypt", no_pad=True)

def aes_ctr(s, key, nonce):
	return xor(s, aes_ctr_keystream(key, nonce))

#misc
def rand_aes_key():
	return os.urandom(16)

def detect_blocksize(oracle):
	initial_size = len(oracle(b""))
	for i in itertools.count(1):
		encrypted = oracle(b"A" * i)
		if len(encrypted) > initial_size:
			return len(encrypted) - initial_size

def detect_ecb(oracle):
	plaintext = b"A" * 64
	blocks = list(map(bytes, grouper(oracle(plaintext), 16, 0)))
	return len(blocks) != len(set(blocks))

def decrypt_ecb_suffix(oracle):
	#see cryptopals #12/#14
	block_size = detect_blocksize(oracle)
	if not detect_ecb(oracle):
		raise ValueError("oracle not using ecb")
	# get prefix length
	for i in range(block_size):
		padding = b"A" * (i + 2 * block_size)
		blocks = list(grouper(oracle(padding), block_size))
		for i, b1, b2 in zip(itertools.count(), blocks, blocks[1:]):
			if b1 == b2:
				common_prefix = padding
				prefix_len = (i + 2) * block_size
				break
		else:
			continue
		break
	length = round_to_multiple(len(oracle(common_prefix)) - prefix_len, block_size)
	known = bytearray()
	for j in range(length):
		prefix = common_prefix + b"A" * (length - j - 1)
		encrypted = oracle(prefix)[:length + prefix_len]
		
		for c in range(256):
			encrypted2 = oracle(prefix + known + bytes((c, )))[:length + prefix_len]
			if encrypted == encrypted2:
				known.append(c)
				break
	return bytes(known)

#var names from https://robertheaton.com/2013/07/29/padding-oracle-attack/
#sometimes messes up on the last block in case it accidentally gets the correct padding
def decrypt_cbc_padding_oracle(ct, iv, padding_oracle):
	blocks = list(map(bytes, grouper(ct, 16)))
	blocks.insert(0, iv)
	pt_blocks = []
	for c1, c2 in zip(blocks, blocks[1:]):
		pt_block = bytearray()  # reversed
		intermediate_block = bytearray()  # reversed
		for i in range(1, 17):
			for c in range(256):
				c1_ = c1[:-i] + bytes([c]) + xor(itertools.repeat(i), reversed(intermediate_block))
				if padding_oracle(c2, c1_):
					intermediate_byte = c ^ i
					pt_byte = c1[-i] ^ intermediate_byte
					pt_block.append(pt_byte)
					intermediate_block.append(intermediate_byte)
					break
		pt_blocks.append(bytes(reversed(pt_block)))
	return unpad_pkcs7(b"".join(pt_blocks))

def decrypt_fixed_nonce_ctr(strs):
	# see cryptopals #20
	blocks_lists = [grouper(s, 16, 0) for s in strs]
	transposed_blocks = zip(*blocks_lists)
	plaintexts = [b"" for _ in range(len(strs))]
	for blocks in transposed_blocks:
		plaintext, _ = decrypt_repeating_key_xor(
			b"".join(map(bytes, blocks)), min_len=16, max_len=16, keysizes_to_try=1
		)
		# chunksize isn't 16 to account for non-16 length on last blocks
		plaintext_parts = grouper(plaintext, len(plaintext) // len(strs))
		for i, part in enumerate(plaintext_parts):
			plaintexts[i] += bytes(part)
	return plaintexts
