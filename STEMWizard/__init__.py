import os
from datetime import datetime
from pprint import pprint

import pandas as pd
import requests
import yaml
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
    from .utils import get_region_info, get_csrf_token  # , _getStudentData, _extractStudentID

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
        else:
            self.googleapi = None
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

    def studentSync(self, cache_file_name='caches/student_data.json', download=True, upload=True):
        '''
        sync student files from STEM Wizard to local filesystem and then up to Google Drive

        :param cache_file_name: filename
        :param download:
        :param upload:
        :return:
        '''
        threads = {
            #                         caches/student_project_data.json
            'project': {'cachefile': 'caches/student_project_data.json',
                        'max_cache_age': 9000,
                        'function': lambda: self.getProjectInfo()},
            'form': {'cachefile': 'caches/student_form_data.json',
                     'max_cache_age': 12000,
                     'function': lambda: self.get_files_and_forms()},
            'file': {'cachefile': 'caches/student_file_data.json',
                     'max_cache_age': 9000,
                     'function': lambda: self.getJudgesMaterials()},
        }

        # fetch data from project, forms and files, and files for judges tabs on milestones page,
        # by div/category for performance
        data = {}
        for k, v in threads.items():
            data[k] = read_json_cache(v['cachefile'], max_cache_age=v['max_cache_age'])
            if len(data[k]) == 0:
                data[k] = v['function']()
                write_json_cache(data[k], v['cachefile'])

        # combine dictionaries into a single view of student metadata
        data = self._merge_dicts(data)
        write_json_cache(data['all'], 'caches/student_data.json')

        # code around bug on milestones page which fails to differentiate files uploaded by separate team members.
        data['fixed'] = read_json_cache('caches/student_data_fixed.json', max_cache_age=9000)
        if len(data['fixed']) == 0:
            data['fixed'] = self._patch_team_filepaths(data['all'])
            write_json_cache(data['fixed'], 'caches/student_fixed.json')
        write_json_cache(data['all'], 'caches/student_data_unpatched.json')
        data['all'] = data['fixed']


        # generate local names for the files and forms
        data['localized'] = self.analyze_local_files(data['all'])
        write_json_cache(data['localized'], 'caches/student_data.json')

        if download:
            self.download_em(data['localized'])
            data['localized'] = self.sync_to_google(data['all'])
        if upload:
            write_json_cache(data['localized'], 'caches/student_data.json')

        return data['localized']

    def _patch_team_filepaths(self, data):
        # gross, but works.  Patches around a bug on the STEM Wizard milestones page which displays the same link for each team member for files
        # that are unique to that team members (ISEF-1b & Participant Signature Page), by using the AJAX fetch of this information from the forms and files page
        for k, v in tqdm(data.items(), desc='patch team files'):
            if len(v['First Name']) > 1:
                self.logger.info(f'patching file info for {k} {v["Project Number"]}')
                updated = self._student_file_detail(k, None)
                for filetype in ['ISEF-1b', 'Participant Signature Page']:
                    for attr in ['url', 'remote_filename']:
                        v['files'][filetype][attr] = []
                        for rows in updated.values():
                            for row in rows:
                                try:
                                    if row['FILE TYPE'] == filetype:
                                        if type(row['FILE NAME']) == dict and attr in row['FILE NAME'].keys():
                                            v['files'][filetype][attr].append(row['FILE NAME'][attr])
                                except:
                                    pprint(row)
                                    pass
        return data

    def analyze_local_files(self, data):
        # dir = f"files/{self.region_domain}"
        dir = ''
        for k, v in data.items():
            project_number = v['Project Number']
            v['participants'] = len(v['Last Name'])
            try:
                div, cat, no = project_number.split('-')
            except:
                cat = 'uncategorized'
                no = k
                if 'Ele' in v['Division']:
                    div = 'ELE'
                elif 'Jun' in v['Division']:
                    div = 'JR'
                elif 'Sen' in v['Division']:
                    div = 'SR'
                else:
                    print(f"unhandled division {v['Division']}")
                    pprint(v)
                    raise
            for filetype, filedata in v['files'].items():
                # ELE-BIOS-001_Participant Signature Page.pdf
                prefix = filetype
                for remote_filename, lastname, firstname in zip(filedata['remote_filename'], v['Last Name'],
                                                                v['First Name']):
                    if len(remote_filename) == 0:
                        continue
                    if len(filedata['remote_filename']) > 1:
                        prefix = f"{filetype}_{lastname}_{firstname}"
                    else:
                        prefix = filetype
                    atoms = remote_filename.split('.')
                    filedata['local_filename'].append(
                        f"{div}/{cat}/{project_number}/{project_number}_{prefix}.{atoms[-1]}")
                for filepath in filedata['local_filename']:
                    fullpath = f"files/ncsef/{filepath}"
                    if os.path.exists(fullpath):
                        filedata['local_lastmod'].append(datetime.fromtimestamp(os.path.getmtime(fullpath)))

                    else:
                        filedata['local_lastmod'].append(None)
        return data

    def sync_to_google(self, data):
        for k, v in data.items():
            for filetype, filedata in v['files'].items():
                for (local_filename, local_lastmod) in zip(filedata['local_filename'], filedata['local_lastmod']):
                    if filetype in ['Abstract Form', '1C', '7']:  # duplicated on judge screen
                        continue
                    self.googleapi.create_file(
                        f"files/ncsef/{local_filename}",
                        f"/Automation/ncsef/by project/{local_filename}")
                    # jkl = self.googleapi._find_file(f"/Automation/ncsef/by project/{local_filename}")
        return data

    def download_em(self, data):
        for id, v in tqdm(data.items()):
            for filetype, filedata in v['files'].items():
                if filetype in ['Abstract Form', '1C', '7']:  # duplicated on judge screen
                    continue
                if len(filedata['url']) > 0:
                    for (url, local_filename, local_lastmod) in zip(filedata['url'], filedata['local_filename'],
                                                                    filedata['local_lastmod']):
                        if 'amazonaws.com' in url and local_lastmod is None:
                            self.download_from_s3(url, local_filename)
                else:
                    for (remote_filename, local_filename, local_lastmod) in zip(filedata['remote_filename'],
                                                                                filedata['local_filename'],
                                                                                filedata['local_lastmod']):
                        if len(remote_filename) > 0 and local_lastmod is None:
                            self.download_from_stemwizard(remote_filename, local_filename)

    def _merge_dicts(self, data):
        '''
        merges the file information found
        :param data:
        :return:
        '''
        data['all'] = data['project']  # use project meta data from project tab
        for tab_name in ['file', 'form']:
            for studentid, studentdata in data[tab_name].items():
                if studentid not in data['all'].keys():
                    data['all'][studentid] = {}
                if 'files' in studentdata.keys():
                    if 'files' not in data['all'][studentid].keys():
                        data['all'][studentid]['files'] = {}
                    j = data['all'][studentid]
                    data['all'][studentid]['files'] = data['all'][studentid]['files'] | studentdata['files']
                else:
                    data['all'] = data['all'] | studentdata
        write_json_cache(data['all'], 'caches/student_data.json')
        return data

    def get_files_and_forms(self):
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

    def download_from_s3(self, url, local_filename):
        # self.logger.debug(f"DownloadFileFromS3Bucket: downloading {url} to {local_dir} as {local_filename} from S3")
        r = self.session.get(url)

        if r.status_code >= 300:
            self.logger.error(f"status code {r.status_code} on post to {url}")
            return

        return self._download_to_local_file_path(local_filename, r)

    def download_from_stemwizard(self, filename_remote, local_file_path, remotedir='images/milestone_uploads',
                                 referer='FilesAndForms'):
        # self.logger.debug(f"downloading {filename_remote}")
        self.get_csrf_token()
        headers['X-CSRF-TOKEN'] = self.csrf
        headers['Referer'] = f'{self.url_base}f/fairadmin/{referer}'
        url = f'{self.url_base}/fairadmin/fileDownload'

        payload = {'_token': self.token,
                   'download_filen_path': '/EBS-Stem/stemwizard/webroot/stemwizard/public/assets/images/milestone_uploads',
                   'download_hideData': filename_remote,
                   }

        rf = self.session.post(url, data=payload, headers=headers)
        if rf.status_code >= 300:
            self.logger.error(f"status code {rf.status_code} on post to {url}")
            return
        return self._download_to_local_file_path(local_file_path, rf)

    def _download_to_local_file_path(self, full_pathname, r):
        atoms = full_pathname.split('/')
        dir = f"files/{self.region_domain}"
        for ele in atoms[:-1]:
            dir += f"/{ele}"
            os.makedirs(dir, exist_ok=True)

        if r.status_code >= 300:
            raise Exception(f'{r.status_code}')
        if r.headers['Content-Type'] == 'text/html':
            self.logger.error(f"failed to download {full_pathname}")
        else:
            f = open(f"files/{self.region_domain}/{full_pathname}", 'wb')
            for chunk in r.iter_content(chunk_size=512 * 1024):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
            f.close()
            self.logger.info(f"download_to_local_file_path: downloaded to {full_pathname}")

    def _student_file_detail(self, studentId, info_id):
        self.get_csrf_token()
        url = f'{self.url_base}/filesAndForms/studentFormsAndFilesDetailedView'
        payload = {'studentId': studentId, 'info_id': info_id}

        headers['X-CSRF-TOKEN'] = self.csrf
        headers['Referer'] = f'{self.url_base}/filesAndForms'
        headers['X-Requested-With'] = 'XMLHttpRequest'
        rfaf = self.session.post(url, data=payload, headers=headers)
        if rfaf.status_code >= 300:
            self.logger.error(f"status code {rfaf.status_code} on post to {url}")
            return
        if info_id is None:
            self.logger.debug(f"getting student info ids for  {studentId}")
            # fp = open('foo.html', 'w')
            # fp.write(rfaf.text)
            # fp.close()
            soup = BeautifulSoup(rfaf.text, 'html.parser')
            # <li class="student_tab" id="64585">
            students = soup.find_all('li', {'class': 'student_tab'})
            data = {}
            for student in students:
                infoid = student['id']
                if infoid is not None:
                    data[f"{studentId} {infoid}"] = self._student_file_detail(studentId, infoid)
        else:
            self.logger.debug(f"getting file info for {studentId} {info_id}")
            data = []
            soup = BeautifulSoup(rfaf.text, 'html.parser')
            # <table class="table table-striped table-bordered table-hover dataTable" style="width:100%;position: relative;border:1px solid #e4e4e4">
            thetable = soup.find('table', {'class': "table table-striped table-bordered table-hover dataTable"})
            # thead = thetable.find('thead')
            th_labels = []
            for th in thetable.find_all('th'):
                th_labels.append(th.text)
            # tbody = thetable.find('tbody')
            for tr in thetable.find_all('tr'):
                row = {}
                for label, td in zip(th_labels, tr.find_all('td')):
                    l = td.find('a')
                    if l is not None:
                        # <a href="#" title="Download" downloadprojfile="McMichael Student Checklist.jpg" downloadprojfilename="McMichael Student Checklist_67263_164437473362.jpg" uploaddocname="https://stem-s3-2021.s3.us-west-1.amazonaws.com/2021/production/project_files/McMichael Student Checklist_67263_164437473362.jpg" class="downloadProjStudent" id="downloadProjStudent" style="text-decoration:none">                            McMichael Student Checklist.jpg</a>
                        if l.has_attr('uploaddocname'):
                            # downloadable from s3 bucket
                            row[label] = {'url': l['uploaddocname'], 'remote_filename': l['downloadprojfilename']}
                        else:
                            # downloadable from STEM Wizard site
                            row[label] = {'remote_filename': l['uploaded_file_name']}

                    else:
                        contents = td.text
                        if label == 'FILE TYPE':
                            # normalize file types
                            contents = contents.replace('2022 NCSEF ', '')
                            contents = contents.replace('Abstract Form', 'Abstract')
                            contents = contents.replace('ISEF ', 'ISEF-')
                            if 'Research Plan' in contents:
                                contents = 'Research Plan'
                        row[label] = contents.strip()
                if len(row):
                    data.append(row)
        return data
