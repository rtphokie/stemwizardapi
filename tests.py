import unittest
from pprint import pprint
from STEMWizard import STEMWizardAPI
import os

configfile = 'stemwizardapi.yaml'


class MyTestCase(unittest.TestCase):

    def test_create_student(self):
        uut = STEMWizardAPI(configfile=configfile)
        data={}
        uut.create_student(data)


    def test_setcolumns(self):
        # results are not really testable in this context, so looking for exceptions here
        uut = STEMWizardAPI(configfile=configfile)
        for listname in ['judge', 'student', 'volunteer']:
            uut.set_columns(listname=listname)

    def test_login(self):
        uut = STEMWizardAPI(configfile=configfile)
        self.assertTrue(uut.authenticated)
        self.assertEqual(40, len(uut.token))
        self.assertGreaterEqual(len(uut.domain), 4)
        self.assertGreaterEqual(int(uut.region_id), 4000)

    def test_xls(self):
        uut = STEMWizardAPI(configfile=configfile)
        filename, df = uut.export_student_list()
        self.assertGreater(len(filename), 30)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 3, 'fewer students than expected')
        self.assertGreaterEqual(df.shape[1], 4, 'fewer columns than expected')

    def test_student_data(self):
        uut = STEMWizardAPI(configfile=configfile)

        data = uut.student_status(fileinfo=True, download=True)
        self.assertGreaterEqual(len(data), 3)
        self.assertGreaterEqual(len(data[list(data.keys())[0]]['files']), 5)

    def test_file_detail(self):
        uut = STEMWizardAPI(configfile=configfile)
        data = uut.student_file_detail(53240, 61630)
        self.assertGreaterEqual(len(data), 3)

    def test_export(self):
        uut = STEMWizardAPI(configfile=configfile)
        filename, df = uut.export_list(listname='judge')
if __name__ == '__main__':
    unittest.main()
