from pprint import pprint
import requests
from bs4 import BeautifulSoup
import pandas as pd
import olefile
import os
import yaml

pd.set_option('display.max_columns', None)
session = requests.Session()  # shared session, maintains cookies throughout
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
        self.region_domain = None
        self.region_id = None
        self.csrf = {}  # assuming Cross Site Request Forgery prevention tokens are on a per endpoint basis.
        self.username = None
        self.password = None

        self._read_config(configfile)
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
        r = session.get(url, headers=headers, allow_redirects=True)

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
            raise ValueError('region id not found on login page')
        if data['region_domain'] is not None:
            self.region_domain = data['region_domain']
        else:
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

        rp = session.post(url_login, data=payload, headers=headers, allow_redirects=True)  # , cookies=session_cookies)
        # self.token = token
        # self.region_id = payload['region_id']
        authenticated = rp.status_code == 200
        return authenticated

    def export_student_list(self, purge_file=False):
        if self.token is None:
            raise ValueError('no token found in object, login before calling export_student_list')
        payload = {'_token': self.token,
                   'filetype': 'xls',
                   'orderby1': '',
                   'sortby1': '',
                   'searchhere1': '',
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

        rf = session.post(f'{self.url_base}/fairadmin/export_file', data=payload, headers=headers, stream=True)
        pprint(rf.headers)
        local_filename = rf.headers['Content-Disposition'].replace('attachment; filename="', '').rstrip('"')

        fp = open(local_filename, 'wb')
        for chunk in rf.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                fp.write(chunk)
        fp.flush()
        fp.close()

        ole = olefile.OleFileIO(local_filename)
        df = pd.read_excel(ole.openstream('Workbook'), engine='xlrd')

        if purge_file:
            try:
                os.remove(local_filename)
            except OSError as e:
                print(f'failed to remove {local_filename} {e}')

        return (local_filename, df)

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
        self.get_csrf_token(endpoint=endpoint)
        headers['X-CSRF-TOKEN'] = self.csrf[endpoint]
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

        r1 = session.post(url, data=payload, headers=headers)
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
        r2 = session.post(url2, data=payload, headers=headers)
        if r2.status_code != 200:
            raise ValueError(f"status code {r2.status_code} from POST to {url2}")

    def export_judge_list(self, purge_file=False):
        self.set_judge_columns()
        if self.token is None:
            raise ValueError('no token found in object, login before calling export_student_list')
        payload = {'_token': self.token,
                   'filetype': 'xls',
                   'orderby1': '',
                   'sortby1': '',
                   'searchhere1': '',
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

        url = f'{self.url_base}/fairadmin/export_file_judge'
        rf = session.post(url, data=payload, headers=headers, stream=True)
        if rf.status_code != 200:
            raise ValueError(f"status code {rf.status_code}")
        pprint(rf.headers)
        local_filename = rf.headers['Content-Disposition'].replace('attachment; filename="', '').rstrip('"')

        self._download_file(local_filename, rf)
        rf.close()

        df = self.xlsfile_to_df(local_filename)

        if purge_file:
            self._safe_rm_file(local_filename)

        return (local_filename, df)

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

    def get_csrf_token(self, endpoint='filesAndForms'):
        if endpoint not in self.csrf.keys():
            self.csrf[endpoint] = None
        if self.csrf[endpoint] is None:
            url = f'{self.url_base}/{endpoint}'
            r = session.get(url, headers=headers)
            soup = BeautifulSoup(r.text, 'lxml')
            csrf = soup.find('meta', {'name': 'csrf-token'})
            if csrf is not None:
                self.csrf[endpoint] = csrf.get('content')

    def student_status(self, debug=True, fileinfo=False, download=True):
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
        self.get_csrf_token(endpoint='filesAndForms')

        r = session.post(f'{self.url_base}/filesAndForms/getStudentData', data=payload, headers=headers, stream=True)

        soup = BeautifulSoup(r.text, 'lxml')
        body = soup.find('tbody')
        rows = body.find_all('tr')
        data = {}
        for row in rows:
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
                               'stud_approval_status': None}
            for cell in cells:
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
            if fileinfo:
                data[studentid]['files'] = self.student_file_detail(studentid, data[studentid]['student_info_id'],
                                                                    download=download)
        return data

    def student_file_detail(self, studentId, info_id, download=True):
        print(f"getting file details for {studentId}")
        self.get_csrf_token(endpoint='filesAndForms')
        url = f'{self.url_base}/filesAndForms/studentFormsAndFilesDetailedView'
        payload = {'studentId': studentId, 'info_id': info_id}

        headers['X-CSRF-TOKEN'] = self.csrf['filesAndForms']
        headers['Referer'] = f'{self.url_base}/filesAndForms'
        headers['X-Requested-With'] = 'XMLHttpRequest'
        rfaf = session.post(url, data=payload, headers=headers)
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
                    data[filetype] = {'file_url': None, 'file_status': None}
                elif n == 1:
                    # get download link from 2nd column
                    linkele = cell.find('a', {'class': 'downloadProjStudent'})
                    if linkele:
                        data[filetype]['file_url'] = linkele.get('uploaddocname')
                    value = cell.text.strip()
                elif n == 5:
                    approved_by, approved_on = cell.find('div').encode_contents().decode('utf-8').split('<br/>')
                    data[filetype]['approved_by'] = approved_by.replace("b'", "")
                    data[filetype]['approved_on'] = approved_on

                else:
                    value = cell.text.strip()
                if value is not None:
                    data[filetype][params[n]] = value
            if download and data[filetype]['file_status'] in ['SUBMITTED', 'APPROVED']:
                DownloadFile(data[filetype]['file_url'], f"{studentId}/{filetype.replace(' ', '_')}",
                             data[filetype]['file_name'])
        return data


def DownloadFile(url, local_dir, local_filename, parent_dir='files'):
    print(f"  downloading {local_filename} into {local_dir}")
    os.makedirs(f"{parent_dir}/{local_dir}", exist_ok=True)
    r = session.get(url)
    f = open(f"{parent_dir}/{local_dir}/{local_filename}", 'wb')
    for chunk in r.iter_content(chunk_size=512 * 1024):
        if chunk:  # filter out keep-alive new chunks
            f.write(chunk)
    f.close()
    return local_filename


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='synchronize with STEM Wizard')
    parser.add_argument('--files', help='fetch files and forms', action='store_true')
    parser.add_argument('--student', help='gather student data', action='store_true')
    parser.add_argument('--judge', help='gather judge data', action='store_true')
    parser.add_argument('--volunteer', help='gather volunteer data', action='store_true')

    parser.add_argument('--sum', dest='accumulate', action='store_const',
                        const=sum, default=max,
                        help='sum the integers (default: find the max)')

    args = parser.parse_args()
    if args.judge:
        raise ValueError("judge automation not implemented")
    if args.volunteer:
        raise ValueError("volunteer automation not implemented")
