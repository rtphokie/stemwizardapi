import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from .categories import categories
from .fileutils import read_json_cache, write_json_cache
from .google_sync import NCSEFGoogleDrive
from .logstuff import get_logger
from .utils import headers

pd.set_option('display.max_columns', None)


class STEMWizardAPI(object):
    from .get_data import getStudentData_by_category, student_folder_links, download_student_files_locally, \
        download_files_locally, DownloadFileFromS3Bucket, DownloadFileFromSTEMWizard, _download_to_local_file_path, \
        analyze_student_data, student_file_info, getFormInfo, process_student_data_row, student_file_detail
    from .fileutils import read_config, write_json_cache, read_json_cache
    from .utils import get_region_info, get_csrf_token, _getStudentData, _extractStudentID

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

        self.get_csrf_token()

        return authenticated

    # def syncStudents(self, cache_file_name='caches/studentData.json'):
    #     # get basic data about students, names, school, overall approval status
    #     data_cache = self.getStudentData_by_category()
    #     data_cache = self.student_file_info(data_cache, cache_file_name)
    #     self.student_folder_links(data_cache)
    #     data_cache = self.download_student_files_locally(data_cache)
    #     write_json_cache(data_cache, cache_file_name)
    #     # self.sync_students_to_google_drive(data_cache)
    #     return data_cache

    def studentSync(self, cache_file_name='caches/student_data.json'):
        data_project = self.getProjectInfo()
        write_json_cache(data_project, 'caches/student_project_data.json')
        data_forms = self.getFilesAndForms()
        write_json_cache(data_forms, 'caches/student_form_data.json')
        data_files= self.getJudgesMaterials()
        write_json_cache(data_files, 'caches/student_file_data.json')

        # merge
        student_data={}
        for studentid in data_project.keys():
            student_data[studentid]=data_project[studentid].copy()
            if studentid in data_forms.keys():
                student_data[studentid]['files']=data_forms[studentid]['files'].copy()
            if studentid in data_files.keys():
                student_data[studentid]['files'].update(data_files[studentid]['files'])
        write_json_cache(data_files, 'caches/student_data.json')
        return student_data

    def getFilesAndForms(self):
        data = {}
        headers['X-CSRF-TOKEN'] = self.csrf
        for category_id, category_title in tqdm(categories.items()):
            payload = {'page': 1,
                       'per_page': 999,
                       'st_stmile_id': 1337,
                       'mileName': 'Files and Forms',
                       'division': 0,
                       'category_select': category_id,
                       }
            url = f'{self.url_base}/fairadmin/getstudentCustomMilestoneDetailView'
            r = self.session.post(url, data=payload, headers=headers)
            soup = BeautifulSoup(r.text, 'lxml')
            head = soup.find('thead')
            th_labels = []
            for th in head.find_all('th'):
                v = th.text.strip()
                v = v.replace('2022 NCSEF ', '')
                if 'Research' in v:
                    v = 'Research Plan'
                th_labels.append(v)

            body = soup.find('tbody')
            for row in body.find_all('tr'):
                import uuid
                studentid = f"unknown_{uuid.uuid4()}"
                studentdata = {'studentid': None, 'files': {}}
                for header in th_labels[6:]:
                    studentdata['files'][header] = {'url': None}
                for n, td in enumerate(row.find_all('td')):
                    if n < 5:
                        studentdata[th_labels[n]] = td.text.strip().replace(" \n\n", ', ')
                        a = td.find('a')
                        if a:
                            l = a['href']
                            atoms = l.split('/')
                            studentid = atoms[-2]
                            studentdata['studentid'] = studentid
                    else:
                        a = td.find('a')
                        if a:
                            studentdata['files'][th_labels[n]] = {'url': a['href']}
                data[studentid] = studentdata
        return data

    def getJudgesMaterials(self):
        data = {}
        headers['X-CSRF-TOKEN'] = self.csrf
        for category_id, category_title in tqdm(categories.items()):
            url = f'{self.url_base}/fairadmin/getstudentCustomMilestoneDetailView'
            params = f'page=1&category_select={category_id}&per_page=999&st_stmile_id=3153'
            r = self.session.post(f"{url}?{params}", headers=headers)
            soup = BeautifulSoup(r.text, 'lxml')
            head = soup.find('thead')
            th_labels = []
            for th in head.find_all('th'):
                hasp = th.find('p')
                if hasp:
                    v = th.find('p').text.strip()
                else:
                    v = th.text.strip()
                v = v.replace('2022 NCSEF ', '')
                for shortname in ['Research Paper', 'Abstract', 'Quad Chart', 'Lab Notebook ',
                                  'Project Presentation Slides', '1 minute video', '1C', '7']:
                    if shortname.lower() in v.lower():
                        v = shortname
                th_labels.append(v)
            body = soup.find('tbody')
            for row in body.find_all('tr'):
                import uuid
                studentid = f"unknown_{uuid.uuid4()}"
                studentdata = {'studentid': None, 'files': {}}
                for header in th_labels[6:]:
                    studentdata['files'][header] = {'url': None, 'filename': None}
                for n, td in enumerate(row.find_all('td')):
                    if n < 5:
                        studentdata[th_labels[n]] = td.text.strip().replace(" \n\n", ', ')
                        a = td.find('a')
                        if a:
                            l = a['href']
                            atoms = l.split('/')
                            studentid = atoms[-2]
                            studentdata['studentid'] = studentid
                    else:
                        # /EBS-Stem/stemwizard/webroot/stemwizard/public/assets/images/milestone_uploads
                        a = td.find('a')
                        if a:
                            studentdata['files'][th_labels[n]] = {'url': a['href']}
                        else:
                            studentdata['files'][th_labels[n]] = {'filename': td.text}
                data[studentid] = studentdata
        return data

    def getProjectInfo(self):
        data = {}
        headers['X-CSRF-TOKEN'] = self.csrf
        for category_id, category_title in tqdm(categories.items()):
            url = f'{self.url_base}/fairadmin/getstudentCustomMilestoneDetailView'
            params = f'page=1&category_select=&child_fair_select=&searchhere=&orderby=&sortby=&division=&class_id=&per_page=50&student_completion_status=undefined&admin_status=undefined&student_checkin_status=&student_milestone_status=&st_stmile_id=1335&grade_select=&student_activation_status=&student_activation_status=1'
            r = self.session.post(f"{url}?{params}", headers=headers)
            soup = BeautifulSoup(r.text, 'lxml')
            head = soup.find('thead')
            th_labels = []
            for th in head.find_all('th'):
                hasp = th.find('p')
                if hasp:
                    v = th.find('p').text.strip()
                else:
                    v = th.text.strip()
                v = v.replace('2022 NCSEF ', '')
                for shortname in ['Research Paper', 'Abstract', 'Quad Chart', 'Lab Notebook ',
                                  'Project Presentation Slides', '1 minute video', '1C', '7']:
                    if shortname.lower() in v.lower():
                        v = shortname
                th_labels.append(v)
            body = soup.find('tbody')
            for row in body.find_all('tr'):
                studentid = row['id'].replace('updatedStudentDiv_', '')
                data[studentid] = {}
                for n, td in enumerate(row.find_all('td')):
                    divs = td.find_all('div')
                    if divs and th_labels[n] != 'Project Name':
                        data[studentid][th_labels[n]] = []
                        for div in divs:
                            data[studentid][th_labels[n]].append(div.text.strip())
                    elif th_labels[n] == 'Project Name':
                        p = td.find('p')
                        if p:
                            data[studentid][th_labels[n]] = p.text.strip()
                        else:
                            data[studentid][th_labels[n]] = td.text.strip()
                    else:
                        data[studentid][th_labels[n]] = td.text.strip()
        return data
