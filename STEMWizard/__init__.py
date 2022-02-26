import os
import pandas as pd
import requests
from tqdm import tqdm
from .categories import categories
from .fileutils import read_json_cache, write_json_cache
from .google_sync import NCSEFGoogleDrive
from .logstuff import get_logger
from .utils import headers

pd.set_option('display.max_columns', None)


class STEMWizardAPI(object):
    from .get_data import getStudentData_by_category, student_folder_links, download_student_files_locally, download_files_locally, DownloadFileFromS3Bucket, DownloadFileFromSTEMWizard, _download_to_local_file_path
    from .fileutils import read_config
    from .utils import get_region_info, get_csrf_token

    def __init__(self, configfile='stemwizardapi.yaml', login_stemwizard=True, login_google=True):
        '''
        initiates a session using credentials in the specified configuration file
        Note that this user must be an administrator on the STEM Wizard site.
        :param configfile: configfile: (default to stemwizardapi.yaml)
        '''
        self.authenticated = None
        self.session = requests.Session()  # shared session, maintains cookies throughout
        # self.session = requests_cache.CachedSession('caches/STEMWizardAPI_http_cache')
        self.region_domain = 'unknown'
        self.parent_file_dir = 'files'
        self.region_id = None
        self.csrf = None
        self.username = None
        self.password = None
        if login_google:
            self.googleapi = NCSEFGoogleDrive()
        self.read_config(configfile)
        self.logger = get_logger(self.domain)
        if self.username is None or len(self.username) < 6:
            raise ValueError(f'did not find a valid username in {configfile}')
        if self.password is None or len(self.password) < 6:
            raise ValueError(f'did not find a valid password in {configfile}')
        self.url_base = f'https://{self.domain}.stemwizard.com'

        self.get_region_info()

        if login_stemwizard:
            self.authenticated = self.login()

        if self.region_domain != self.domain:
            raise ValueError(
                f'STEM Wizard returned a region domain of {self.region_domain}, which varies from the {self.domain} value in the config file')

    def __del__(self):
        self.session.close()
        self.logger.info(f"destroyed session with {self.domain}")

    def login(self):
        '''
        authenticates
        :return:
        '''
        if self.region_id is None:
            self.get_region_info()

        payload = {'region_domain': self.domain,
                   'region_id': self.region_id,
                   'region': self.region_domain,
                   '_token': self.token,
                   'username': self.username,
                   'password': self.password}

        url_login = f'{self.url_base}/admin/authenticate'

        rp = self.session.post(url_login, data=payload, headers=headers,
                               allow_redirects=True)  # , cookies=session_cookies)
        if rp.status_code >= 300:
            self.logger.error(f"status code {rp.status_code} on post to {url_login}")
            return

        # self.token = token
        # self.region_id = payload['region_id']
        authenticated = rp.status_code == 200
        if authenticated:
            self.logger.info(f"authenticated to {self.domain}")
        else:
            self.logger.error(f"failed to authenticate to {self.domain}")

        return authenticated

    def analyze_student_data(self, data_cache):
        idstofetchfiledetailfor = set()
        for studentid, data_student in tqdm(data_cache.items(), desc='student json'):
            student_local_dir = f"files/{self.region_domain}/{studentid}"
            os.makedirs(student_local_dir, exist_ok=True)
            jsonfilename = f"{student_local_dir}/{data_student['l_name']},{data_student['f_name']}.json"
            jsonfilename = jsonfilename.replace("\n", ',')
            jsonfilename = jsonfilename.replace("  ", '')
            jsonfilename = jsonfilename.replace(" ", '')
            write_json_cache(data_student, jsonfilename)
            if len(data_student['files']) == 0:
                idstofetchfiledetailfor.add(studentid)
        return idstofetchfiledetailfor

    def student_file_info(self, data_cache, cache_file_name):
        idstofetchfiledetailfor = self.analyze_student_data(data_cache)
        for studentid in tqdm(idstofetchfiledetailfor, 'student file data'):
            data_cache[studentid]['files'] = self.student_file_detail(studentid,
                                                                      data_cache[studentid]['student_info_id'])
        write_json_cache(data_cache, cache_file_name)
        return data_cache

    def syncStudents(self, cache_file_name='caches/studentData.json'):
        # get basic data about students, names, school, overall approval status
        data_cache = self.getStudentData_by_category()
        data_cache = self.student_file_info(data_cache, cache_file_name)
        self.student_folder_links(data_cache)
        self.download_student_files_locally(data_cache)
        # self.sync_students_to_google_drive(data_cache)
        # self._write_to_cache(data_cache, cache_file_name)
        return data_cache
