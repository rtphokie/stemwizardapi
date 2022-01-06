import unittest
from pprint import pprint
from STEMWizard import StemWizard
import os

class MyTestCase(unittest.TestCase):
    def test_config(self):
        uut = StemWizard()
        self.assertEqual(uut.username, 'rtphokie')
        self.assertGreaterEqual(len(uut.password), 0)

    def test_login(self):
        uut = StemWizard()
        self.assertEqual(40, len(uut.token))
        self.assertGreaterEqual(len(uut.domain), 4)
        self.assertGreaterEqual(int(uut.region_id), 4000)

    def test_xls(self):
        uut = StemWizard()
        filename, df = uut.export_student_list()
        self.assertGreater(len(filename), 30)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 3, 'fewer students than expected')
        self.assertGreaterEqual(df.shape[1], 32, 'fewer columns than expected')

    def test_student_data(self):
        uut = StemWizard()
        data = uut.student_status(fileinfo=True, download=False)
        pprint(data)

    def test_file_detail(self):
        uut = StemWizard()
        data = uut.student_file_detail(53240, 61630)
        self.assertGreaterEqual(len(data), 3)


if __name__ == '__main__':
    unittest.main()
