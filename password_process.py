import os
import hashlib

def password_processor(password: str):
  salt = os.urandom(16)
  hashed_password = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
  return (salt + hashed_password).hex()

def password_verifier(dbpassword_hex, provided_password: str):
  dbpassword = bytes.fromhex(dbpassword_hex)
  salt = dbpassword[:16]
  hash_password = dbpassword[16:]
  check_hash = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt, 100000)

  return check_hash == hash_password