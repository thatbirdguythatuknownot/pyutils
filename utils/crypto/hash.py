import itertools

from utils.bits import rol
from utils.itertools2 import grouper
from utils.crypto.xor import xor

def sha1_padding(msg, forced_len=None):
	if forced_len is None:
		msg_len = len(msg) * 8
	else:
		msg_len = forced_len * 8
	m = -(msg_len + 1 + 64) % 512
	msg = (msg + bytes([0b10000000]) + b"\x00" * (m // 8) + msg_len.to_bytes(8, byteorder="big"))
	return msg

def sha1(msg, state=None, msg_added_len=None):  #pylint: disable=too-many-locals
	if state is None:
		h0 = 0x67452301
		h1 = 0xEFCDAB89
		h2 = 0x98BADCFE
		h3 = 0x10325476
		h4 = 0xC3D2E1F0
	else:
		h0, h1, h2, h3, h4 = state
	max_word = 0xFFFFFFFF
	if msg_added_len is None:
		msg = sha1_padding(msg)
	else:
		forced_len = len(msg) + msg_added_len
		msg = sha1_padding(msg, forced_len)
	for chunk in map(bytes, grouper(msg, 512 // 8)):
		words = [
			int.from_bytes(c, byteorder="big", signed=False)
			for c in map(bytes, grouper(chunk, 32 // 8))
		] + [-1] * (80 - 16)
		for i in range(16, 80):
			words[i] = rol(words[i - 3] ^ words[i - 8] ^ words[i - 14] ^ words[i - 16], 1, 32)
		a = h0
		b = h1
		c = h2
		d = h3
		e = h4
		for i in range(80):
			if i < 20:
				f = (b & c) | ((~b) & d)
				k = 0x5A827999
			elif i < 40:
				f = b ^ c ^ d
				k = 0x6ED9EBA1
			elif i < 60:
				f = (b & c) | (b & d) | (c & d)
				k = 0x8F1BBCDC
			else:
				f = b ^ c ^ d
				k = 0xCA62C1D6
			temp = (rol(a, 5, 32) + f + e + k + words[i]) & max_word
			e = d
			d = c
			c = rol(b, 30, 32)
			b = a
			a = temp
		h0 = (h0 + a) & max_word
		h1 = (h1 + b) & max_word
		h2 = (h2 + c) & max_word
		h3 = (h3 + d) & max_word
		h4 = (h4 + e) & max_word
	return b"".join(h.to_bytes(4, byteorder="big") for h in (h0, h1, h2, h3, h4))

def secret_prefix_mac(msg, key, hash_func=sha1):
	return hash_func(key + msg)

def sha1_hash_extension(orig_msg, new_msg, oracle, key_lens=None):
	orig_hash = oracle(orig_msg)
	if key_lens is None:
		key_lens = itertools.count(1)
	for key_len in key_lens:
		glue_padding = sha1_padding(b"\x00" * key_len + orig_msg)[key_len + len(orig_msg):]
		msg_added_len = key_len + len(orig_msg) + len(glue_padding)
		state = [int.from_bytes(c, byteorder="big") for c in grouper(orig_hash, 4)]
		forged_mac = sha1(new_msg, state, msg_added_len)
		forged_msg = orig_msg + glue_padding + new_msg
		if oracle(forged_msg) == forged_mac:
			return (forged_msg, forged_mac)
	raise ValueError("No key_len is valid")

def hmac(key, msg, hash_func, block_size=64):
	if len(key) > block_size:
		key = hash_func(key)
	elif len(key) < block_size:
		key = key.ljust(block_size, b"\x00")
	outer_key = xor(key, b"\x5c" * block_size)
	inner_key = xor(key, b"\x36" * block_size)
	return hash_func(outer_key + hash_func(inner_key + msg))
