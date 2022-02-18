from bs4 import BeautifulSoup
from pprint import pprint
import json
import olefile
import os
import pandas as pd
import requests, requests_cache
import time
import yaml
from STEMWizard.google_sync import NCSEFGoogleDrive
from STEMWizard.logstuff import get_logger
import os
from tqdm import tqdm
from datetime import timedelta

# from requests_toolbelt import MultipartEncoder

pd.set_option('display.max_columns', None)
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36'}


class STEMWizardAPI(object):

    def __init__(self, configfile='stemwizardapi.yaml'):
        '''
        initiates a session using credentials in the specified configuration file
        Note that this user must be an administrator on the STEM Wizard site.
        :param configfile: configfile: (default to stemwizardapi.yaml)
        '''
        self.authenticated = None
        # self.session = requests.Session()  # shared session, maintains cookies throughout
        self.session = requests_cache.CachedSession('STEMWizardAPI_http_cache',
            # cache_control=True,  # Use Cache-Control headers for expiration, if available
            expire_after=timedelta(minutes=30),  # Otherwise expire responses after one day
            allowable_methods=['POST'],
            allowable_codes=[200],  # Cache 400 responses as a solemn reminder of your failures
            # match_headers=True,  # Match all request headers
            stale_if_error=True
        )
        self.region_domain = 'unknown'
        self.parent_file_dir = 'files'
        self.region_id = None
        self.csrf = None
        self.username = None
        self.password = None
        self.googleapi = NCSEFGoogleDrive()

        self._read_config(configfile)
        self.logger = get_logger(self.domain)
        if self.username is None or len(self.username) < 6:
            raise ValueError(f'did not find a valid username in {configfile}')
        if self.password is None or len(self.password) < 6:
            raise ValueError(f'did not find a valid password in {configfile}')
        self.url_base = f'https://{self.domain}.stemwizard.com'

        self._get_region_info()

        self.authenticated = self.login()

        if self.region_domain != self.domain:
            raise ValueError(
                f'STEM Wizard returned a region domain of {self.region_domain}, which varies from the {self.domain} value in the config file')

    def __del__(self):
        self.session.close()
        self.logger.info(f"destroyed session with {self.domain}")

    def _read_config(self, configfile):
        '''
        reads named yaml configuration file
        :param configfile: (defaulted to stemwizardapi.yaml above)
        :return: nothing, updates username, password and token attribuates on the object
        '''
        fp = open(configfile, 'r')
        data_loaded = yaml.safe_load(fp)
        self.domain = data_loaded['domain']
        self.username = data_loaded['username']
        self.password = data_loaded['password']
        fp.close()

    def _get_region_info(self):
        '''
        gets admin login page, scrapes region and token info for later use
        :return: nothing, updates region_id, region_domain, and token parameters on object
        '''
        url = f'{self.url_base}/admin/login'
        r = self.session.get(url, headers=headers, allow_redirects=True)
        if r.status_code >= 300:
            self.logger.error(f"status code {r.status_code} on post to {url}")
            return

        # scrape token
        soup = BeautifulSoup(r.text, 'html.parser')
        token_ele = soup.find('input', {'name': '_token'})
        token = token_ele.get('value')
        self.token = token

        # scrape region info
        data = {'region_id': None, 'region_domain': None}
        for x in soup.find_all('input'):
            if 'region' in x.get('name'):
                data[x.get('name')] = x.get('value')
        if data['region_id'] is not None:
            self.region_id = data['region_id']
        else:
            self.logger.error(f"region id not found on login page")
            raise ValueError('region id not found on login page')
        if data['region_domain'] is not None:
            self.region_domain = data['region_domain']
        else:
            self.logger.error(f"region domain not found on login page")
            raise ValueError('region domain not found on login page')

    def login(self):
        '''
        authenticates
        :return:
        '''
        if self.region_id is None:
            self._get_region_info()

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
            self.logger.error(f"status code {rp.status_code} on post to {url}")
            return

        # self.token = token
        # self.region_id = payload['region_id']
        authenticated = rp.status_code == 200
        if authenticated:
            self.logger.info(f"authenticated to {self.domain}")
        else:
            self.logger.error(f"failed to authenticate to {self.domain}")

        return authenticated

    def export_list(self, listname, purge_file=False):
        '''
        Google prefers all excel files to have an xlsx extension
        :param listname: student, judge, or volunteer
        :param purge_file: delete local file when done, default: false
        :return:
        '''
        if self.token is None:
            raise ValueError('no token found in object, login before calling export_student_list')
        self.set_columns(listname)
        payload = {'_token': self.token,
                   'filetype': 'xls',
                   'orderby1': '',
                   'sortby1': '',
                   'searchhere1': ''
                   }
        if listname == 'student':
            remotepath = f'/Automation/{self.domain}/by student/student list.xlsx'
            url = f'{self.url_base}/fairadmin/export_file'
            payload_specific = {
                'category_select1': '',
                'round2_category_select1': '',
                'child_fair_select1': '',
                'status_select1': '',
                'division1': 0,
                'classperiod_select1': '',
                'student_completion_status1': '',
                'student_checkin_status1': '',
                'student_activation_status1': '',
                'management_user_type_id1': ' 1',
                'checked_fields': '',
                'class_id1': '',
                'admin_status1': '',
                'final_status1': '',
                'files_approval_status1': '',
                'project_status1': '',
                'project_score': '',
                'last_year': '',
            }
        elif listname == 'judge':
            remotepath = f'/Automation/{self.domain}/by judge/judge list.xlsx'
            url = f'{self.url_base}/fairadmin/export_file_judge'
            payload_specific = {
                'category_select1': '',
                'judge_types1': '',
                'status_select1': '',
                'final_assigned_category_select1': '',
                'division_judge1': 0,
                'assigned_division1': 0,
                'special_awards_judge1': '',
                'assigned_lead_judge1': '',
                'judge_checkin_status1': '',
                'judge_activation_status1': '',
                'checked_fields_header': '',
                'checked_fields': '',
                'class_id1': '',
                'last_year': '',
                'dashBoardPage1': '',
            }
        elif listname == 'volunteer':
            remotepath = f'/Automation/{self.domain}/volunteer list.xlsx'
            url = f'{self.url_base}/fairadmin/exportVolunteerExcelPdf'
            payload_specific = {
                'searchhere1': '',
                'registration_status1': '',
                'last_year': '',
            }

        else:
            raise ValueError(f"unknown list {listname}")
        payload.update(payload_specific)

        self.logger.debug(f'posting to {url} using {listname} params')
        rf = self.session.post(url, data=payload, headers=headers, stream=True)
        if rf.status_code >= 300:
            self.logger.error(f"status code {rf.status_code} on post to {url}")
            return
        filename_suggested = rf.headers['Content-Disposition'].replace('attachment; filename="', '').rstrip('"')
        self.logger.info(f'receiving {filename_suggested}')
        filename_local = f'{self.parent_file_dir}/{self.domain}/{listname}_list.xls'

        fp = open(filename_local, 'wb')
        for chunk in rf.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                fp.write(chunk)
        fp.flush()
        fp.close()

        ole = olefile.OleFileIO(filename_local)
        df = pd.read_excel(ole.openstream('Workbook'), engine='xlrd')

        self.googleapi.create_file(filename_local, remotepath)
        if purge_file:
            try:
                os.remove(filename_local)
            except OSError as e:
                print(f'failed to remove {filename_local} {e}')
        return (filename_local, df)

    def set_columns(self, listname='judge'):
        '''
        there's lots of if-then-else going on here because of inconsistencies in naming across
        STEM Wizard, still worth centralizing setting all columns to be visible across judge, student, and volunteer lists

        :param listname: expects, judge, volunteer, or student
        :return: nothing
        '''
        if listname == 'volunteer':
            endpoint = 'fairadmin/volunteers'
        else:
            endpoint = f'fairadmin/{listname}'
        self.get_csrf_token()
        headers['X-CSRF-TOKEN'] = self.csrf
        headers['Referer'] = f'{self.url_base}f/fairadmin/{listname}'
        headers['X-Requested-With'] = 'XMLHttpRequest'

        # https://ncregtest.stemwizard.com/fairadmin/showVolunteerList
        # https://ncregtest.stemwizard.com/fairadmin/showVolunteerList

        # build list URL, these aren't consistently named
        if listname == 'judge':
            url = f'{self.url_base}/fairadmin/ShowJudgesList'
            payload = {'per_page': 50,
                       'page': 1,
                       'searchhere': '',
                       'category_select': '',
                       'judge_types': '',
                       'judge_activation_status': '',
                       'status_select': '',
                       'final_assigned_category_select': '',
                       'special_awards_judge': '',
                       'final_status': '',
                       'division_judge': 0,
                       'assigned_division': 0,
                       'judge_checkin_status': '',
                       'division': 0,
                       'last_year': '',
                       'dashBoardPage': '',
                       'assigned_lead_judge': ''
                       }
        elif listname == 'student':
            url = f'{self.url_base}/fairadmin/ShowStudentList'
            payload = {
                'page': 1,
                'searchhere': '',
                'category_select': '',
                'round2_category_select': '',
                'child_fair_select': '',
                'status_select': '',
                'class_id': '',
                'student_completion_status': '',
                'files_approval_status': '',
                'final_status': '',
                'project_status': '',
                'admin_status': '',
                'student_checkin_status': '',
                'student_activation_status': '',
                'division': 0,
                'project_score': '',
                'last_year': '',
                'round_select': '',
            }
        elif listname == 'volunteer':
            url = f'{self.url_base}/fairadmin/showVolunteerList'
            payload = {'per_page': 999,
                       'page': 1,
                       'searchhere': '',
                       'registration_status': '', 'last_year': ''
                       }
        else:
            raise ValueError(f'unhandled list name {listname} in set_columns')

        r1 = self.session.post(url, data=payload, headers=headers)
        if r1.status_code != 200:
            raise ValueError(f"status code {r1.status_code}")

        # find the column codes
        soup = BeautifulSoup(r1.text, 'lxml')
        all_columns = set()
        for ele in soup.find_all('input', {'class', 'ace chkslct'}):
            all_columns.add(ele.get('value'))
        payload = {'checked_fields': ','.join(all_columns),
                   'region_id': self.region_id,
                   'management_user_type_id': 3}

        # set all columns to be visible
        url2 = f'{self.url_base}/fairadmin/saveStudentColumnSettings'
        r2 = self.session.post(url2, data=payload, headers=headers)
        if r2.status_code != 200:
            raise ValueError(f"status code {r2.status_code} from POST to {url2}")

    def xlsfile_to_df(self, local_filename):
        ole = olefile.OleFileIO(local_filename)
        df = pd.read_excel(ole.openstream('Workbook'), engine='xlrd')
        return df

    def _safe_rm_file(self, local_filename):
        try:
            os.remove(local_filename)
        except OSError as e:
            print(f'failed to remove {local_filename} {e}')

    def _download_file(self, local_filename, rf):
        fp = open(local_filename, 'wb')
        for chunk in rf.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                fp.write(chunk)
        fp.flush()
        fp.close()

    def get_csrf_token(self):
        if self.csrf is not None:
            self.logger.debug(f"using existing CSRF token")
        else:
            url = f'{self.url_base}/filesAndForms'
            r = self.session.get(url, headers=headers)
            if r.status_code >= 300:
                self.logger.error(f"status code {r.status_code} on post to {url}")
                return
            soup = BeautifulSoup(r.text, 'lxml')
            csrf = soup.find('meta', {'name': 'csrf-token'})
            if csrf is not None:
                self.csrf = csrf.get('content')
            self.logger.debug(f"gathered CSRF token {self.csrf}")

    def student_status(self, debug=True, fileinfo=False, download=True, force_file_detail_fetch=False):
        cache_filename = 'student_data_cache.json'
        cache = self._read_cache(cache_filename, 600)

        self.logger.debug(f"in student_status, fileinfo {fileinfo}, download {download}")
        payload = {'_token': self.token,
                   'page': 1,
                   'category_select': '',
                   'searchhere': '',
                   'status_select': 'undefined',
                   'research_plan_student_status': 'undefined',
                   'orderby': 'files_approval_status',
                   'sortby': '',
                   'reg_sel': 'undefined',
                   'teacher_id': 'undefined',
                   'all_forms_status': '',
                   'form_selected': 'undefined',
                   'class_winner': 'undefined',
                   'school_id_dropdownvalue': 'undefined',
                   'form_selected_status': 'undefined',
                   'child_fair_select': '',
                   'per_page': 999,
                   'hidden_school_id': 'undefined',
                   'hidden_region_id': self.region_id,
                   'student_completion_status': '',
                   'files_approval_status': '',
                   'final_status': '',
                   'project_status': '',
                   'admin_status': '',
                   'division': 0,
                   'from_page': 'FAIRADMIN',
                   'student_activation_status': '',
                   }
        self.get_csrf_token()

        url = f'{self.url_base}/filesAndForms/getStudentData'
        r = self.session.post(url, data=payload, headers=headers, stream=True)
        if r.status_code >= 300:
            self.logger.error(f"status code {r.status_code} on post to {url}")
            return

        soup = BeautifulSoup(r.text, 'lxml')
        body = soup.find('tbody')
        rows = body.find_all('tr')
        data = {}
        self.logger.info(f"got StudentData for {int(len(rows)/2)} students")
        for cnt, row in enumerate(rows):
            studentid = row.get('id')
            if studentid is None or 'updatedStudentDiv_' not in studentid:
                continue
            else:
                studentid = studentid.replace('updatedStudentDiv_', '')
            cells = row.find_all('td')
            data[studentid] = {'f_name': None,
                               'l_name': None,
                               'teacherfullname': None,
                               'project_name': None,
                               'Project': None,
                               'project_no': None,
                               'stud_chk': None,
                               'origin_fair': None,
                               'admin_status': None,
                               'stud_com_status': None,
                               'stud_approval_status': None,
                               'files': {}}
            for cell in cells:
                self.process_student_data_row(cell, data, studentid)
            if data[studentid]['f_name'] == 'Judy' and data[studentid]['l_name'] == 'Test':
                continue
            jkl = f"{self.parent_file_dir}/{self.region_domain}/{studentid}/{data[studentid]['l_name']}_{data[studentid]['f_name']}.json"


            if fileinfo:
                self.sync_student_files_from_stem_wizard(studentid, data[studentid], download, force_file_detail_fetch)
            else:
                # get file details from individual cache if skipping the expensive ajax call
                if os.path.isfile(jkl):
                    data[studentid] = json.load(jkl)
            cache[studentid]=data[studentid]
            print(f"{100 * ((cnt + 1) / len(rows)):3.0f}% {studentid} {data[studentid]['f_name'][:10]:10}", end=" ")
            print(f"{data[studentid]['l_name'][:10]:10}", end=" ")
            print(f"{data[studentid]['stud_approval_status'][:10]:10}", end=" ")
            print(f"{data[studentid]['origin_fair'][:20]:10}", end=" ")
            print()
            self._write_to_cache(data[studentid], jkl)

        self._write_to_cache(cache, cache_filename)

        return data

    def _write_to_cache(self, cache, cache_filename):
        fp = open(cache_filename, 'w')
        json.dump(cache, fp, indent=2)
        fp.close()

    def _read_cache(self, cache_filename, max_cache_age=600):
        try:
            if os.path.isfile(cache_filename):
                st = os.stat(cache_filename)
                age = (time.time() - st.st_mtime)
            else:
                age = 999999999999999
            if age < max_cache_age:
                fp = open(cache_filename, 'r')
                cache = json.loads(fp.read())
                fp.close()
            else:
                cache = {}
        except Exception as e:
            print(e)
            cache = {}
        return cache

    def process_student_data_row(self, cell, data, studentid):
        id = cell.get('id')
        param = cell.get('class')
        if type(param) is list:
            param = param[0]
        if id is not None and param is None:
            param = id
        value = cell.text.strip()
        link = cell.find('a')
        if link is not None:
            student_info_id = link.get('student_info_id')
            if student_info_id:
                data[studentid]['student_info_id'] = student_info_id
        elif param is None:
            param = 'project_name'
        if param:
            param = param.replace(f"click_class", '').replace(f'_{studentid}', '')
            data[studentid][param] = value

    def sync_student_files_to_google_drive(self, node, studentid):
        for formname, formdata in node['files'].items():
            self.googleapi.create_folder(f"/Automation/{self.domain}/by internal id/{studentid}/{formname}")
            # print(formname, formdata['file_name'])
            localpath = f"files/{studentid}/{formname}/{formdata['file_name']}"
            remotepath = f"/Automation/{self.domain}/by internal id/{id}/{formname}/{formdata['file_name']}"
            self.googleapi.create_file(localpath, remotepath)
    def sync_student_files_from_stem_wizard(self, studentid, studentdata, download, force_file_detail_fetch):
        if studentdata['stud_com_status'] != 'Complete' or force_file_detail_fetch:
            self.logger.debug(f"making AJAX call for finfo for {studentid} {studentdata['f_name']} {studentdata['l_name']}")
            studentdata['files'] = self.student_file_detail(studentid, studentdata['student_info_id'])

            for documenttype, filedata in studentdata['files'].items():
                if download and filedata['file_status'] in ['SUBMITTED', 'APPROVED']:
                    if 'https' not in filedata['file_name'] and filedata['uploaded_file_name'] is not None:
                        # pprint(filedata)
                        fn = self.DownloadFileFromSTEMWizard(filedata['file_name'],
                                                             filedata['uploaded_file_name'],
                                                             f"{studentid}/{documenttype.replace(' ', '_')}" )
                    elif 'https' in filedata['file_url']:
                                                             fn = self.DownloadFileFromS3Bucket(filedata['file_url'],
                                                             f"{studentid}/{documenttype.replace(' ', '_')}",
                                                             filedata['file_name'])
                    else:
                        pprint(filedata)
                        self.logger.error(f"could not determine download for student {studentid} {documenttype}")

    def student_file_detail(self, studentId, info_id, ):
        self.logger.debug(f"getting file details for {studentId}")
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
        fp = open('foo.html', 'w')
        fp.write(rfaf.text)
        fp.close()

        soup = BeautifulSoup(rfaf.text, 'html.parser')
        table = soup.find('table')
        rows = table.find_all('tr')
        data = {}
        params = []
        thead = table.find('thead')
        cells = thead.find_all('th')
        for cell in cells:
            params.append(cell.text.strip().lower().replace(' ', '_'))
        for row in rows[1:]:
            cells = row.find_all('td')
            for n, cell in enumerate(cells):
                value = None
                if n == 0:
                    filetype = cell.text.strip()
                    if 'Research Plan' in filetype:
                        filetype = 'Research Plan'
                    data[filetype] = {'file_url': None, 'file_status': None, 'uploaded_file_name': None}
                elif n == 1:
                    # get download link from 2nd column
                    linkele = cell.find('a', {'class': 'downloadProjStudent'})
                    if linkele:
                        data[filetype]['file_url'] = linkele.get('uploaddocname')
                    else:
                        linkele = cell.find('a', {'class': 'file_download'})
                        if linkele:
                            data[filetype]['uploaded_file_name'] = linkele.get('uploaded_file_name')
                    value = cell.text.strip()
                elif n == 5:
                    approved_by, approved_on = cell.find('div').encode_contents().decode('utf-8').split('<br/>')
                    data[filetype]['approved_by'] = approved_by.replace("b'", "")
                    data[filetype]['approved_on'] = approved_on

                else:
                    value = cell.text.strip()
                if value is not None:
                    data[filetype][params[n]] = value

        return data

    def download_to_local_file_path(self, local_dir, local_filename, parent_dir, r, force_download=False):
        target_dir = f"{parent_dir}/{self.region_domain}/{local_dir}"
        full_pathname = f"{target_dir}/{local_filename}"
        if not os.path.isfile(full_pathname):
            os.makedirs(target_dir, exist_ok=True)
            if r.status_code >= 300:
                raise Exception(f'{r.status_code}')
            f = open(full_pathname, 'wb')
            for chunk in r.iter_content(chunk_size=512 * 1024):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
            f.close()
            self.logger.info(f"downloaded to {full_pathname} forced {force_download}")
        else:
            self.logger.debug(f"using existing {full_pathname}")

    def DownloadFileFromS3Bucket(self, url, local_dir, local_filename, parent_dir=f'files'):
        self.logger.debug(f"downloading {url} to {local_dir} as {local_filename} from S3")
        r = self.session.get(url)
        if r.status_code >= 300:
            self.logger.error(f"status code {r.status_code} on post to {url}")
            return
        self.download_to_local_file_path(local_dir, local_filename, parent_dir, r)
        return local_filename

    def DownloadFileFromSTEMWizard(self, original_file, uploaded_file_name, local_dir, parent_dir=f'files'):
        self.logger.debug(f"downloading {original_file} to {local_dir} as {original_file} from STEMWizard")
        self.get_csrf_token()
        headers['X-CSRF-TOKEN'] = self.csrf
        headers['Referer'] = f'{self.url_base}f/fairadmin/ilesAndForms'
        headers['X-Requested-With'] = 'XMLHttpRequest'
        url = f'{self.url_base}/fairadmin/fileDownload'

        payload = {'_token': self.token,
                   'download_filen_path': '/EBS-Stem/stemwizard/webroot/stemwizard/public/assets/uploads/project_files',
                   'download_hideData': uploaded_file_name,
                   }

        rf = self.session.post(url, data=payload, headers=headers)
        if rf.status_code >= 300:
            self.logger.error(f"status code {rf.status_code} on post to {url}")
            return
        self.download_to_local_file_path(local_dir, original_file, parent_dir, rf)
        return original_file
#
# if __name__ == '__main__':
#     parser = argparse.ArgumentParser(description='synchronize with STEM Wizard')
#     parser.add_argument('--files', help='fetch files and forms', action='store_true')
#     parser.add_argument('--student', help='gather student data', action='store_true')
#     parser.add_argument('--judge', help='gather judge data', action='store_true')
#     parser.add_argument('--volunteer', help='gather volunteer data', action='store_true')
#
#     parser.add_argument('--sum', dest='accumulate', action='store_const',
#                         const=sum, default=max,
#                         help='sum the integers (default: find the max)')
#
#     args = parser.parse_args()
#     if args.judge:
#         raise ValueError("judge automation not implemented")
#     if args.volunteer:
#         raise ValueError("volunteer automation not implemented")
