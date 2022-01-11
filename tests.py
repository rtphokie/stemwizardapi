import unittest
from pprint import pprint
from STEMWizard import STEMWizardAPI, google_sync
from STEMWizard.google_sync import NCSEFGoogleDrive
import os

configfile = 'stemwizardapi.yaml'


class GoogleSheetsSyncTestCases(unittest.TestCase):

    def test_sheet(self):
        sheet = google_sync.get_sheet('NCSEF 2022 student list')


class GoogleDriveSyncTestCases(unittest.TestCase):

    def test_createfile(self):
        uut = NCSEFGoogleDrive()
        localpath = 'files/53240/ISEF_1/ISEF_1.pdf'
        remotepath = '/Automation/ncregtest/ISEF_1.pdf'
        uut.create_file(localpath, remotepath)

    def test_drive_dump(self):
        uut = NCSEFGoogleDrive()
        print(uut)

    def test_find_file(self):
        uut = NCSEFGoogleDrive()
        node = uut.get_id_by_path('/Automation/ncsef/by project')
        # self.assertEqual('1a8mTh8qSxFmJ7vOf3rHUsNn62lzFjYPC', node['id'])

    def test_create_folder(self):
        uut = NCSEFGoogleDrive()
        # uut.list_all(cache_update_ttl=0)
        data = {'ELE': ['BioS', 'Chem', 'EaEn', 'EnTe', 'PhyM'],
                'JR': ['BSA', 'BSB', 'CHE', 'EES', 'ENG', 'MAT', 'PHY', 'TEC'],
                'SR': ['BSA', 'BSB', 'CHE', 'EES', 'ENG', 'MAT', 'PHY', 'TEC']
                }
        uut.list_all(cache_update_ttl=0)
        for fair in ['ncsef', 'ncsefreg1', 'ncsefreg3a', 'ncsefreg7']:
            for orgmethod in ['by category', 'by internal id', 'by judge', 'by student name', 'by project']:
                uut.create_folder(f'/Automation/{fair}/{orgmethod}')
            for division in data.keys():
                uut.create_folder(f'/Automation/{fair}/by category/{division}', refresh=False)
                for category in data[division]:
                    uut.create_folder(f'/Automation/{fair}/by category/{division}/{category}', refresh=False)

        uut.list_all(cache_update_ttl=0)

    def test_drive_dump_specific_folde(self):
        uut = NCSEFGoogleDrive()
        uut.dump('/Automation/ncsefreg7')


class STEMWizardAPITestCases(unittest.TestCase):

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

    def test_student_xls(self):
        uut = STEMWizardAPI(configfile=configfile)
        filename, df = uut.export_list('student')
        self.assertGreater(len(filename), 30)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 3, 'fewer students than expected')
        self.assertGreaterEqual(df.shape[1], 33, 'fewer columns than expected')

    def test_judge_xls(self):
        uut = STEMWizardAPI(configfile=configfile)
        filename, df = uut.export_list('judge')
        self.assertGreater(len(filename), 30)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 1, 'fewer judges than expected')
        self.assertGreaterEqual(df.shape[1], 26, 'fewer columns than expected')

    def test_volunteer_xls(self):
        uut = STEMWizardAPI(configfile=configfile)
        filename, df = uut.export_list('volunteer')
        self.assertGreater(len(filename), 30)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 1, 'fewer volunteer than expected')
        self.assertGreaterEqual(df.shape[1], 14, 'fewer columns than expected')

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
