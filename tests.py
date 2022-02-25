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

    def test_find_file(self):
        fullpath = "/Automation/ncsef"
        id = '1l704Kp_kNVsPT9Idx-AuLb2cYUYaYOjL'
        uut = NCSEFGoogleDrive()
        # find a node by fullpath name
        nodeid, parentid, parentpath, title, isafolder = uut._find_file(fullpath)
        self.assertEqual(id, nodeid)

        # remove that id , and search again without refresh, should not be found
        del uut.ids[id]
        # pprint( uut.ids[id])
        nodeid, parentid, parentpath, title, isafolder = uut._find_file(fullpath, refresh=False)
        self.assertIsNone(nodeid)
        # now allow refresh to happen, should be found
        nodeid, parentid, parentpath, title, isafolder = uut._find_file(fullpath, refresh=True)
        self.assertEqual(id, nodeid)

        f"/Automation/ncsef/by student/ Schmidt, Garrett",
        nodeid, parentid, parentpath, title, isafolder = uut._find_file(fullpath)
        print(nodeid)

    def test_jkl(self):
        uut = NCSEFGoogleDrive()
        uut.create_folder('/Automation/ncsef/by internal id/32773')
        nodeid, parentid, parentpath, title, isafolder = uut._find_file('/Automation/ncsef/by internal id/32773')
        print(f"nodeid:     {nodeid}")
        print(f"parentid:   {parentid}")
        print(f"parentpath: {parentpath}")
        print(f"parentpath: {title}")
        print(f"isafolder:  {isafolder}")

    def test_create_link(self):
        uut = NCSEFGoogleDrive()
        uut.create_shortcut('/Automation/ncsef/by internal id/54484/2022_NCSEF_Participant_Signature_Page.pdf',
                            '/Automation/ncsef/by student')
        return
        targetid = '18-zaJt213NcAS7xy0Il-bhfkidJm1X3V'
        parentid = '1jcV_rVYKHvfg6V50qwSPeSsavc-ovuU2'
        shortcut_metadata = {
            "name": "Shortcut",
            'mimeType': 'application/vnd.google-apps.shortcut',
            "parents": [{"id": parentid}],
            "shortcutDetails": {"targetId": targetid,
                                "targetMimeType": 'application/vnd.google-apps.folder'}
        }
        shortcut = uut.drive.CreateFile(shortcut_metadata)
        shortcut.Upload()
        pprint(shortcut)
        print(f"fileid:   {shortcut.get('id')}")
        print(f"targetId: {shortcut.get('targetId')}")
        print(f"targetMimeType: {shortcut.get('targetMimeType')}")


class NCSEF_prod_TestCases_operation(unittest.TestCase):

    def dtest_01_setcolumns(self):
        # results are not really testable in this context, so looking for exceptions here
        uut = STEMWizardAPI(configfile=configfile_prod)
        for listname in ['judge', 'student', 'volunteer']:
            uut.set_columns(listname=listname)

    def test_00_login(self):
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
        print(f"Students: {df.shape[0]}")

    def test_judge_xls(self):
        uut = STEMWizardAPI(configfile=configfile_prod)
        filename, df = uut.export_list('judge')
        # print(df)
        self.assertGreater(len(filename), 20)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 50, 'fewer judges than expected')
        self.assertGreaterEqual(df.shape[1], 26, 'fewer columns than expected')
        print(f"Judges: {df.shape[0]}")

    def test_paymentStatus_xls(self):
        uut = STEMWizardAPI(configfile=configfile_prod)
        filename, df = uut.export_list('paymentStatus')
        # print(df)
        self.assertGreater(len(filename), 20)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 50, 'fewer judges than expected')
        self.assertGreaterEqual(df.shape[1], 26, 'fewer columns than expected')
        print(f"Judges: {df.shape[0]}")

    def test_volunteer_xls(self):
        uut = STEMWizardAPI(configfile=configfile_prod)
        filename, df = uut.export_list('volunteer')
        self.assertGreater(len(filename), 29)
        self.assertTrue(os.path.exists(filename))
        self.assertGreaterEqual(df.shape[0], 1, 'fewer volunteer than expected')
        self.assertGreaterEqual(df.shape[1], 14, 'fewer columns than expected')
        print(f"Volunteers: {df.shape[0]}")

    def test_judge_xls2(self):
        uut = STEMWizardAPI(configfile=configfile_prod)
        uut.generate_all_data_report('student')


class devtest(unittest.TestCase):
    def test_google_clean_empty_dirs(self):
        uut = STEMWizardAPI(configfile=configfile_prod, login_stemwizard=False)
        parentid = '1wiIOz_ZdPHoOBNjJcb1HX-L2NqX5urQx'
        ids = set()
        for id, data in uut.googleapi.ids.items():
            if 'folder' not in data['mimeType']:
                continue
            if len(data['parents']) < 1:
                continue
            if data['parents'][0]['id'] != parentid:
                continue  # not in by internal id
            print(data['title'])
            if data['labels']['trashed']:
                pprint(data)
                raise
            ids.add(id)
        print('--' * 20)
        print(len(ids))
        from tqdm import tqdm
        for id in tqdm(ids):
            item = uut.googleapi.drive.CreateFile({'id': data['id']})
            item.Trash()

    def test_min_forms(self):
        uut = STEMWizardAPI(configfile=configfile_prod, login_stemwizard=False, login_google=False)
        data_cache = uut.getStudentData_by_category()
        min = {'ISEF 1', 'ISEF 1a', '2022 NCSEF Abstract Form', 'Research Plan', 'ISEF 1b',
               '2022 NCSEF Participant Signature Page'}

        for sid, data in data_cache.items():
            missing=min-set(data['files'].keys())
            print(sid, missing)
            if len(missing) ==0:
                src = f'../files/ncsef/{sid}'
                dst = f"links/{data['l_name']},{data['f_name']}"
                os.symlink(src, dst)

    def test_trashed(self):
        uut = STEMWizardAPI(configfile=configfile_prod, login_stemwizard=False)
        pprint(uut.googleapi.ids['1s9FHLsSeTGJat8qNjIjL2K8zS41VNT9Q'])
        # 1s9FHLsSeTGJat8qNjIjL2K8zS41VNT9Q 58171

    # 1gbq76PiRZykUP3MzRgMoXoZ101CZV7CL 56098
    # 1EoL06eT-e8egvAZ0G1Kxchd_sLqcelg4 56098
    # 1gcYQwyjPH0k0qOqK5nkwsa0ulWLTv7Sj 56098
    # 1qkyVhUv6c2VW_yOXi6wLTB5ySAlC9d8e 56098
    # 15cxytgSbIAs_nvS_t6b2cH1Z666_IIm- 5609

    def dtest1(self):
        from tqdm import tqdm
        data_cache = self.getStudentData_by_category()
        # for sid, data in data_cache.items():


class NCSEF_prod_TestCases(unittest.TestCase):

    def test_student_data(self):
        uut = STEMWizardAPI(configfile=configfile_prod)
        data = uut.getStudentData()
        print(len(data))

    def dtest_sync_to_google_drive(self):
        uut = STEMWizardAPI(configfile=configfile_prod)

        cache_filename = 'student_data_cache.json'
        cache = uut._read_cache(cache_filename, 6000)
        pprint(cache.keys())
        uut.sync_student_files_to_google_drive(cache['57344'], 57344)
        # 57344

    def dtest_filedownload_from_stemwizard(self):
        # <a style="cursor: pointer;text-decoration:none;" class="file_download" id="file_download"
        # original_file="Rose Research Plan.docx" uploaded_file_name="Rose Research Plan_63561_164230152536.docx">Rose Research Plan.docx</a>
        url = 'https://ncsef.stemwizard.com/fairadmin/fileDownload'
        uut = STEMWizardAPI(configfile=configfile_prod)
        fn = uut.DownloadFileFromSTEMWizard('Rose Research Plan.doc', 'Rose Research Plan_63561_164230152536.docx')


if __name__ == '__main__':
    unittest.main()
