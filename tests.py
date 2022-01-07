import unittest
from pprint import pprint
from STEMWizard import STEMWizardAPI
import os

class MyTestCase(unittest.TestCase):
    def test_setcolumns(self):
        # results are not really testable in this context, so looking for exceptions here
        uut = STEMWizardAPI(configfile='stemwizardapi.yaml')
        for listname in ['judge', 'student', 'volunteer']:
            uut.set_columns(listname=listname)


    def test_config(self):
        uut = STEMWizardAPI(configfile='stemwizardapi_prod.yaml')
        self.assertEqual(uut.username, 'rtphokie')
        self.assertGreaterEqual(len(uut.password), 0)

    def test_login(self):
        uut = STEMWizardAPI(configfile='stemwizardapi_prod.yaml')
        self.assertTrue(uut.authenticated)
        self.assertEqual(40, len(uut.token))
        self.assertGreaterEqual(len(uut.domain), 4)
        self.assertGreaterEqual(int(uut.region_id), 4000)

    def test_xls(self):
        uut = STEMWizardAPI(configfile='stemwizardapi_prod.yaml')
        filename, df = uut.export_student_list()
        self.assertGreater(len(filename), 30)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 3, 'fewer students than expected')
        self.assertGreaterEqual(df.shape[1], 32, 'fewer columns than expected')

    def test_student_data(self):
        uut = STEMWizardAPI(configfile='stemwizardapi_prod.yaml')
        data = uut.student_status(fileinfo=True, download=False)
        pprint(data)

    def test_file_detail(self):
        uut = STEMWizardAPI()
        data = uut.student_file_detail(53240, 61630)
        self.assertGreaterEqual(len(data), 3)


if __name__ == '__main__':
    unittest.main()
