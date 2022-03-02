import os
from datetime import datetime

import yaml
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
    # from .get_data import getStudentData_by_category, student_folder_links, download_student_files_locally, \
    #     download_files_locally, DownloadFileFromS3Bucket, DownloadFileFromSTEMWizard, _download_to_local_file_path, \
    #     analyze_student_data, student_file_info, getFormInfo, process_student_data_row, student_file_detail
    # from .fileutils import read_config
    from .utils import get_region_info, get_csrf_token#, _getStudentData, _extractStudentID

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
        else:
            self.authenticated = None

        if self.region_domain != self.domain:
            raise ValueError(
                f'STEM Wizard returned a region domain of {self.region_domain}, which varies from the {self.domain} value in the config file')

    def __del__(self):
        self.session.close()
        self.logger.info(f"destroyed session with {self.domain}")

    def read_config(self, configfile):
        """
        reads named yaml configuration file
        :param configfile: (defaulted to stemwizardapi.yaml above)
        :return: nothing, updates username, password and token attribuates on the object
        """
        fp = open(configfile, 'r')
        data_loaded = yaml.safe_load(fp)
        self.domain = data_loaded['domain']
        self.username = data_loaded['username']
        self.password = data_loaded['password']
        fp.close()

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

    def studentSync(self, cache_file_name='caches/student_data.json'):
        threads = {
            #                         caches/student_project_data.json
            'project': {'cachefile': 'caches/student_project_data.json',
                        'max_cache_age': 9000,
                        'function': lambda: self.getProjectInfo()},
            'form': {'cachefile': 'caches/student_form_data.json',
                     'max_cache_age': 12000,
                     'function': lambda: self.getFilesAndForms()},
            'file': {'cachefile': 'caches/student_file_data.json',
                     'max_cache_age': 9000,
                     'function': lambda: self.getJudgesMaterials()},
        }

        # combine dictionaries
        data = {}
        for k, v in threads.items():
            data[k] = read_json_cache(v['cachefile'], max_cache_age=v['max_cache_age'])
            if len(data[k]) == 0:
                data[k] = v['function']()
                write_json_cache(data[k], v['cachefile'])

        data = self.merge_dicts(data)
        write_json_cache(data['all'], 'caches/student_data.json')

        data['localized'] = self.analyze_local_files(data['all'])

        write_json_cache(data['localized'], 'caches/student_data.json')

        # self.download_em(data['localized'])

        return data['localized']

    def analyze_local_files(self, data):
        dir = f"files/{self.region_domain}"
        for k, v in data.items():
            project_number = v['Project Number']
            div, cat, no = project_number.split('-')
            for filetype, filedata in v['files'].items():
                for filedatainstance in filedata['remote_filename']:
                    atoms = filedatainstance.split('.')
                    filedata['local_filename'].append(
                        f"{dir}/{div}/{cat}/{project_number}/{project_number}_{filetype}.{atoms[-1]}")
                for filepath in filedata['local_filename']:
                    if os.path.exists(filepath):
                        filedata['local_lastmod'].append(datetime.fromtimestamp(os.path.getmtime(filepath)))

                    else:
                        filedata['local_lastmod'].append(None)
        return data

    def download_em(self, data):
        for id, v in tqdm(data.items()):
            for filetype, filedata in v['files'].items():
                for (remote_filename, local_filename, local_lastmod) in zip(filedata['remote_filename'], filedata['local_filename'], filedata['local_lastmod']):
                    if local_lastmod is None:
                        self.DownloadFileFromSTEMWizard(remote_filename, local_filename)

    def merge_dicts(self, data):
        data['all'] = data['project']
        for d in ['file', 'form']:
            for k, v in data[d].items():
                if k not in data['all'].keys():
                    data['all'][k] = {}
                if 'files' in v.keys():
                    if 'files' not in data['all'][k].keys():
                        data['all'][k]['files'] = {}
                    j = data['all'][k]
                    data['all'][k]['files'] = data['all'][k]['files'] | v['files']
                else:
                    data['all'] = data['all'] | v
        write_json_cache(data['all'], 'caches/student_data.json')
        return data

    def getFilesAndForms(self):
        if not self.authenticated:
            self.authenticated = self.login()
        data = {}
        headers['X-CSRF-TOKEN'] = self.csrf
        for category_id, category_title in tqdm(categories.items(), desc='Files and Forms'):
            payload = {'page': 1,
                       'per_page': 999,
                       'st_stmile_id': 1337,
                       'mileName': 'Files and Forms',
                       'division': 0,
                       'category_select': category_id,
                       'student_activation_status': 1,
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
                if len(v) <= 2:
                    v = f"ISEF-{v.lower()}"
                th_labels.append(v)

            body = soup.find('tbody')
            for row in body.find_all('tr'):
                import uuid
                studentid = f"unknown_{uuid.uuid4()}"
                studentdata = {'studentid': None, 'files': {}}
                for header in th_labels[6:]:
                    studentdata['files'][header] = {'url': [], 'remote_filename': [], 'local_filename': [],
                                                    'local_lastmod': []}
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
                        a = td.find_all('a')
                        if a:
                            # studentdata['files'][th_labels[n]] = {'url': []}
                            for link in a:
                                atoms = link['href'].split('/')
                                studentdata['files'][th_labels[n]]['url'].append(link['href'])
                                studentdata['files'][th_labels[n]]['remote_filename'].append(atoms[-1])
                data[studentid] = studentdata
        return data

    def getJudgesMaterials(self):
        if not self.authenticated:
            self.authenticated = self.login()
        data = {}
        headers['X-CSRF-TOKEN'] = self.csrf
        for category_id, category_title in tqdm(categories.items(), desc='judges materials'):

            url = f'{self.url_base}/fairadmin/getstudentCustomMilestoneDetailView'
            params = f'page=1&category_select={category_id}&per_page=999&st_stmile_id=3153&student_activation_status=1'
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
                th_labels.append(v.strip())  # remove stray whitespace in th text
            body = soup.find('tbody')
            for row in body.find_all('tr'):
                studentdata = {'studentid': None, 'files': {}}
                for header in th_labels[5:]:
                    studentdata['files'][header] = {'url': [], 'remote_filename': [],
                                                    'local_filename': [], 'local_lastmod': []}
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
                            studentdata['files'][th_labels[n]]['url'].append(a['href'])
                        else:
                            studentdata['files'][th_labels[n]]['remote_filename'].append(td.text)
                data[studentid] = studentdata
        return data

    def getProjectInfo(self):
        if not self.authenticated:
            self.authenticated = self.login()

        data = {}
        headers['X-CSRF-TOKEN'] = self.csrf
        for category_id, category_title in tqdm(categories.items(), desc='project'):
            url = f'{self.url_base}/fairadmin/getstudentCustomMilestoneDetailView'
            params = f'page=1&category_select={category_id}&child_fair_select=&searchhere=&orderby=&sortby=&division=&class_id=&per_page=999&student_completion_status=undefined&admin_status=undefined&student_checkin_status=&student_milestone_status=&st_stmile_id=1335&grade_select=&student_activation_status=1'
            r = self.session.post(f"{url}?{params}", headers=headers)
            fp = open(f'/tmp/project.html', 'w')
            fp.write(r.text)
            fp.close()
            soup = BeautifulSoup(r.text, 'lxml')
            head = soup.find('thead')
            if head is None:
                print(r.status_code)
                print(r.text)
                raise ValueError(
                    f'no table head found on project tab for {category_title} of getstudentCustomMilestoneDetailView ')
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

    def DownloadFileFromS3Bucket(self, url, local_dir, local_filename, parent_dir=f'files'):
        # self.logger.debug(f"DownloadFileFromS3Bucket: downloading {url} to {local_dir} as {local_filename} from S3")
        r = self.session.get(url)

        if r.status_code >= 300:
            self.logger.error(f"status code {r.status_code} on post to {url}")
            return

        return self._download_to_local_file_path(local_filename, r)

    def DownloadFileFromSTEMWizard(self, filename_remote, uploaded_file_name, remotedir='uploads/project_files', referer='FilesAndForms'):
        # self.logger.debug(f"downloading {filename_remote}")
        self.get_csrf_token()
        headers['X-CSRF-TOKEN'] = self.csrf
        headers['Referer'] = f'{self.url_base}f/fairadmin/{referer}'
        url = f'{self.url_base}/fairadmin/fileDownload'

        payload = {'_token': self.token,
                   'download_filen_path': f'/EBS-Stem/stemwizard/webroot/stemwizard/public/assets/{remotedir}',
                   'download_hideData': filename_remote,
                   }

        rf = self.session.post(url, data=payload, headers=headers)
        if rf.status_code >= 300:
            self.logger.error(f"status code {rf.status_code} on post to {url}")
            return
        return self._download_to_local_file_path(uploaded_file_name, rf)

    def _download_to_local_file_path(self, full_pathname, r):
        if r.status_code >= 300:
            raise Exception(f'{r.status_code}')
        if r.headers['Content-Type'] == 'text/html':
            self.logger.error(f"failed to download {full_pathname}")
        else:
            f = open(full_pathname, 'wb')
            for chunk in r.iter_content(chunk_size=512 * 1024):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
            f.close()
            self.logger.info(f"download_to_local_file_path: downloaded to {full_pathname}")

