import unittest
from pprint import pprint
import requests, requests_cache  # https://requests-cache.readthedocs.io/en/latest/
import random_address
import names
import uuid
requests_cache.install_cache('test_cache', backend='sqlite', expire_after=3600)

def main():
    for i in range(5):
        name = names.get_full_name()
        address = random_address.real_random_address()
        print(name, address)


class MyTestCase(unittest.TestCase):
    def test_names(self):
        main()



if __name__ == '__main__':
    unittest.main()
