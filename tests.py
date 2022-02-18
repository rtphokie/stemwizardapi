import unittest
from pprint import pprint
from STEMWizard import STEMWizardAPI, google_sync
from STEMWizard.google_sync import NCSEFGoogleDrive
import os

configfile = 'stemwizardapi.yaml'
configfile_prod = 'stemwizardapi_ncsef.yaml'


class GoogleSheetsSyncTestCases(unittest.TestCase):

    def test_sheet(self):
        sheet = google_sync.get_sheet('NCSEF 2022 student list')


class GoogleDriveSyncTestCases(unittest.TestCase):

    def destructive_test_updatefile(self):
        uut = NCSEFGoogleDrive()
        localpath = 'files/ncsef/judge_list.xls'
        remotepath = '/Automation/ncsef/by judge/judge list.xls'
        uut.create_file(localpath, remotepath)
        # print(uut)

    def test_drive_dump(self):
        uut = NCSEFGoogleDrive()
        str = uut.__str__()
        lines = str.split("\n")
        self.assertGreaterEqual(len(lines), 125)
        seen = {}
        for x in lines:
            if x not in seen.keys():
                seen[x] = 0
            seen[x] += 1
        self.assertEqual(len(lines), sum(seen.values()))  # ensure each full path shows up just once in output
        print(uut)

    def test_drive_dump_specific_folder(self):
        uut = NCSEFGoogleDrive()
        str = uut.dump('/Automation/ncsef/by category/SR', indent_character=".", show_emoji=True)
        lines = str.split("\n")
        self.assertNotEqual(len(uut.ids), len(lines))
        self.assertIn('📁/Automation/ncsef/by category/SR', lines)
        self.assertIn('.📁/Automation/ncsef/by category/SR/BSA', lines)

    def test_create_folder(self):
        uut = NCSEFGoogleDrive()
        # uut.list_all(cache_update_ttl=0)
        data = {'ELE': ['BioS', 'Chem', 'EaEn', 'EnTe', 'PhyM'],
                'JR': ['BSA', 'BSB', 'CHE', 'EES', 'ENG', 'MAT', 'PHY', 'TEC'],
                'SR': ['BSA', 'BSB', 'CHE', 'EES', 'ENG', 'MAT', 'PHY', 'TEC']
                }
        uut.list_all(cache_update_ttl=0)
        for fair in ['ncsef', 'ncsefreg1', 'ncsefreg3a', 'ncsefreg7', 'ncregtest']:
            for orgmethod in ['by category', 'by internal id', 'by judge', 'by student', 'by project']:
                uut.create_folder(f'/Automation/{fair}/{orgmethod}')
            for division in data.keys():
                uut.create_folder(f'/Automation/{fair}/by category/{division}', refresh=False)
                for category in data[division]:
                    uut.create_folder(f'/Automation/{fair}/by category/{division}/{category}', refresh=False)

        uut.list_all(cache_update_ttl=0)

    def test_create_folder_full(self):
        uut = NCSEFGoogleDrive()
        uut.create_folder('/Automation/ncregtest/by internal id/53240')
        uut.create_folder('/Automation/ncregtest/by internal id/53240/ISEF 1')


class NCRegTestTestCases(unittest.TestCase):

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
        print(filename)
        self.assertGreater(len(filename), 30)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 3, 'fewer students than expected')
        self.assertGreaterEqual(df.shape[1], 33, 'fewer columns than expected')

    def test_judge_xls_prod(self):
        uut = STEMWizardAPI(configfile=configfile_prod)
        filename, df = uut.export_list('judge')
        # print(df)
        self.assertGreater(len(filename), 20)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 1, 'fewer judges than expected')
        self.assertGreaterEqual(df.shape[1], 26, 'fewer columns than expected')

    def test_judge_xls(self):
        uut = STEMWizardAPI(configfile=configfile)
        filename, df = uut.export_list('judge')
        print(df)
        # self.assertGreater(len(filename), 30)
        # self.assertTrue(os.path.exists(filename))
        # self.assertGreaterEqual(df.shape[0], 1, 'fewer judges than expected')
        # self.assertGreaterEqual(df.shape[1], 26, 'fewer columns than expected')

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
        pprint(data)
        return
        for id, node in data.items():
            uut.googleapi.create_folder(f"/Automation/{uut.domain}/by internal id/{id}")
            for formname, formdata in node['files'].items():
                uut.googleapi.create_folder(f"/Automation/{uut.domain}/by internal id/{id}/{formname}")
                # print(formname, formdata['file_name'])
                localpath = f"files/{id}/{formname}/{formdata['file_name']}"
                remotepath = f"/Automation/{uut.domain}/by internal id/{id}/{formname}/{formdata['file_name']}"
                uut.googleapi.create_file(localpath, remotepath)

            # uut.googleapi.create_file()
        self.assertGreaterEqual(len(data), 3)
        self.assertGreaterEqual(len(data[list(data.keys())[0]]['files']), 5)

    def test_file_detail(self):
        uut = STEMWizardAPI(configfile=configfile)
        data = uut.student_file_detail(53240, 61630)
        self.assertGreaterEqual(len(data), 3)

    def test_export(self):
        uut = STEMWizardAPI(configfile=configfile)
        filename, df = uut.export_list(listname='judge')


class NCSEF_prod_TestCases(unittest.TestCase):

    def test_setcolumns(self):
        # results are not really testable in this context, so looking for exceptions here
        uut = STEMWizardAPI(configfile=configfile_prod)
        for listname in ['judge', 'student', 'volunteer']:
            uut.set_columns(listname=listname)

    def test_login(self):
        uut = STEMWizardAPI(configfile=configfile_prod)
        self.assertTrue(uut.authenticated)
        self.assertEqual(40, len(uut.token))
        self.assertGreaterEqual(len(uut.domain), 4)
        self.assertGreaterEqual(int(uut.region_id), 4000)

    def test_student_xls(self):
        uut = STEMWizardAPI(configfile=configfile_prod)
        filename, df = uut.export_list('student')
        self.assertGreater(len(filename), 27)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 3, 'fewer students than expected')
        self.assertGreaterEqual(df.shape[1], 33, 'fewer columns than expected')

    def test_judge_xls(self):
        uut = STEMWizardAPI(configfile=configfile_prod)
        filename, df = uut.export_list('judge')
        # print(df)
        self.assertGreater(len(filename), 20)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 50, 'fewer judges than expected')
        self.assertGreaterEqual(df.shape[1], 26, 'fewer columns than expected')

    def test_volunteer_xls(self):
        uut = STEMWizardAPI(configfile=configfile_prod)
        filename, df = uut.export_list('volunteer')
        self.assertGreater(len(filename), 29)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 1, 'fewer volunteer than expected')
        self.assertGreaterEqual(df.shape[1], 14, 'fewer columns than expected')

    def test_student_data(self):
        uut = STEMWizardAPI(configfile=configfile_prod)

        data = uut.student_status(fileinfo=True, download=True)
        # for id, node in data.items():
        #     print(id)
        #     continue
        #     uut.googleapi.create_folder(f"/Automation/{uut.domain}/by internal id/{id}")
        #     for formname, formdata in node['files'].items():
        #         uut.googleapi.create_folder(f"/Automation/{uut.domain}/by internal id/{id}/{formname}")
        #         # print(formname, formdata['file_name'])
        #         localpath = f"files/{id}/{formname}/{formdata['file_name']}"
        #         remotepath = f"/Automation/{uut.domain}/by internal id/{id}/{formname}/{formdata['file_name']}"
        #         uut.googleapi.create_file(localpath, remotepath)
        #
        #     # uut.googleapi.create_file()
        self.assertGreaterEqual(len(data), 3)
        laststudentid=list(data.keys())[-1]
        pprint(data[laststudentid])
        self.assertGreaterEqual(len(data[laststudentid]['files']), 6)

    def test_sync_to_google_drive(self):
        uut = STEMWizardAPI(configfile=configfile_prod)

        cache_filename = 'student_data_cache.json'
        cache = uut._read_cache(cache_filename, 600)
        pprint(cache)

    def test_filedownload_from_stemwizard(self):
        #<a style="cursor: pointer;text-decoration:none;" class="file_download" id="file_download"
        # original_file="Rose Research Plan.docx" uploaded_file_name="Rose Research Plan_63561_164230152536.docx">Rose Research Plan.docx</a>
        url='https://ncsef.stemwizard.com/fairadmin/fileDownload'
        uut = STEMWizardAPI(configfile=configfile_prod)
        fn = uut.DownloadFileFromSTEMWizard('Rose Research Plan.doc','Rose Research Plan_63561_164230152536.docx')


if __name__ == '__main__':
    unittest.main()
