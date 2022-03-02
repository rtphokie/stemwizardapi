import os
from datetime import datetime
from pprint import pprint

import olefile
import pandas as pd
from bs4 import BeautifulSoup
from dateutil import parser
from tqdm import tqdm

from STEMWizard.categories import categories
from .fileutils import read_json_cache, write_json_cache
from .utils import headers


def getCustomFilesInfo(self):
    payload = {'_token': self.token,
               'filetype': 'excel',
               'st_stmile_id1': 3153,
               }

    url = f'{self.url_base}/fairadmin/exportmilestonereport'

    # pprint(payload)
    # self.logger.debug(f'posting to {url} using {listname} params')
    rf = self.session.post(url, data=payload, headers=headers)
    if rf.status_code >= 300:
        self.logger.error(f"status code {rf.status_code} on post to {url}")
        return
    print(rf.status_code)
    filename_local = '/tmp/CustomMilestoneDetailView.xls'
    fp = open(filename_local, 'wb')
    for chunk in rf.iter_content(chunk_size=1024):
        if chunk:  # filter out keep-alive new chunks
            fp.write(chunk)
    fp.flush()
    fp.close()


def getFormInfo(self, category_id):
    html = self._getStudentData(category_id)
    soup = BeautifulSoup(html, 'lxml')
    body = soup.find('tbody')
    rows = body.find_all('tr')
    data = {}
    for cnt, row in enumerate(rows):
        studentid = self._extractStudentID(row.get('id'))
        if studentid is None:
            continue  # this row contains no student data
        cells = row.find_all('td')
        data[studentid] = {'studentid': studentid,
                           'f_name': None,
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
            data[studentid].update(self.process_student_data_row(cell, studentid))
        if data[studentid]['f_name'] == 'Judy' and data[studentid]['l_name'] == 'Test':
            continue
    return data


def download_custom_files(self, filename_local='/tmp/CustomMilestoneDetailView.xls'):
    all_student_data = self.getStudentData_by_category()

    df = self.xlsfile_to_df(filename_local)
    for n, row in df.iterrows():
        project_no = row[0]
        if pd.isna(project_no):
            continue
        else:
            studentid = self.get_internal_id_from_project_no(all_student_data, project_no)
        filename_quad_chart = row[6]
        filename_slides = row[7]
        url_video = row[8]
        print(studentid, project_no, filename_quad_chart, filename_slides, url_video)
        if pd.notna(filename_quad_chart) and studentid is not None:
            student_local_dir = f"files/{self.region_domain}/{studentid}"
            self.DownloadFileFromSTEMWizard(filename_quad_chart, filename_quad_chart,
                                            student_local_dir,
                                            remotedir='images/milestone_uploads',
                                            referer='studentmilestonereport/region/3153/15257'
                                            )
            # pprint(all_student_data[studentid])
            raise
            # data_student_files_updated = self.sync_student_files_to_google_drive(studentid, data_student['files'])


def sync_students_to_google_drive(self, data_cache):
    for studentid, data_student in tqdm(data_cache.items(), desc='sync to Google Drive'):
        # sync those local file up to Google Drive
        data_student_files_updated = self.sync_student_files_to_google_drive(studentid, data_student['files'])


def download_student_files_locally(self, data_cache):
    updated_student_data = {}
    for studentid, data_student in tqdm(data_cache.items(), desc='sync files locally'):
        # download those files and forms as necessary
        updated_student_data[studentid] = self.download_files_locally(studentid, data_student['files'])
    for studentid, filedata in updated_student_data.items():
        data_cache[studentid]['files'] = filedata
    return data_cache


def student_folder_links(self, data_cache):
    for studentid, data_student in tqdm(data_cache.items(), desc='folder links'):
        if data_student['project_no'] != '':
            try:
                div, cat, _ = data_student['project_no'].split('-')
                remote_div_dir = f"/Automation/{self.region_domain}/by category/{div}"
                self.googleapi.create_folder(remote_div_dir)
                self.googleapi.create_folder(f"{remote_div_dir}/{cat}")
                self.googleapi.create_shortcut(f"/Automation/{self.region_domain}/by internal id/{studentid}",
                                               f"{remote_div_dir}/{cat}", data_student['project_no'])
            except Exception as e:
                pprint(data_student)
                self.logger.error(f"{studentid} {e}")

        self.googleapi.create_shortcut(
            f"/Automation/{self.region_domain}/by internal id/{studentid}",
            f"/Automation/{self.region_domain}/by student",
            f"{data_student['l_name']}, {data_student['f_name']}")


def getStudentData_by_category(self):
    cache_file_name = 'caches/studentData.json'
    data = read_json_cache(cache_file_name, max_cache_age=14400)
    if len(data) == 0:
        data = {}
        pbar = tqdm(len(categories), desc="categories")
        for category_id, category_title in categories.items():
            pbar.set_description(f"{category_title:20}")
            newdata = self.getFormInfo(category_id)
            data.update(newdata)
            pbar.update(1)
            self.logger.info(f"got StudentData for {len(newdata)} students in category {category_title}")
        write_json_cache(data, cache_file_name)
    return data


def process_student_data_row(self, cell, studentid):
    data = {}
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
            data['student_info_id'] = student_info_id
    elif param is None:
        param = 'project_name'
    if param:
        param = param.replace(f"click_class", '').replace(f'_{studentid}', '')
        data[param] = value
    return data


def student_file_detail(self, studentId, info_id):
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
    if thead is None:
        raise Exception('student table not found on files and Forms page')
    else:
        cells = thead.find_all('th')
    for cell in cells:
        params.append(cell.text.strip().lower().replace(' ', '_'))
    for row in rows[1:]:
        cells = row.find_all('td')
        for n, cell in enumerate(cells):
            # 0 type, 1 name, 2 status, 3 approved by, 4 approved dat, 5 updated by, 6 approval status
            value = None
            if n == 0:
                filetype = cell.text.strip()
                if 'Research Plan' in filetype:
                    filetype = 'Research Plan'  # clean up Research Plan filetype
                data[filetype] = {'file_url': None,
                                  'file_status': None,
                                  'updated_on': None,
                                  'updated_by': None,
                                  'approved_on': None,
                                  'approved_by': None,
                                  'uploaded_file_name': None,
                                  'file_name': None}
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
            elif n == 4:
                divele = cell.find('div')
                if divele:
                    approved_by, approved_on = divele.encode_contents().decode('utf-8').split('<br/>')
                    data[filetype]['approved_by'] = approved_by.replace("b'", "")
                    try:
                        data[filetype]['approved_on'] = parser.parse(approved_on)
                    except:
                        data[filetype]['approved_on'] = approved_on
            elif n == 5:
                updated_by, updated_on = cell.find('div').encode_contents().decode('utf-8').split('<br/>')
                data[filetype]['updated_by'] = updated_by.replace("b'", "")
                try:
                    data[filetype]['updated_on'] = parser.parse(updated_on)
                except:
                    data[filetype]['updated_on'] = updated_on
            else:
                value = cell.text.strip()
            if value is not None:
                data[filetype][params[n]] = value

    return data


def sync_student_files_to_google_drive(self, studentid, filedata):
    # Creating a folder for each student and uploading the files to that folder.
    for formname, formdata in filedata.items():
        if formdata['file_name'] == 'NONE':
            continue
        remote_dir = f"/Automation/{self.domain}/by internal id/{studentid}"
        self.googleapi.create_folder(remote_dir)
        localpath = f"{self.parent_file_dir}/{self.domain}/{studentid}/{formdata['file_name']}"
        remotepath = f"{remote_dir}/{formdata['file_name']}"
        try:
            jkl = self.googleapi.create_file(localpath, remotepath)
            self.logger.info(f"uploaded to {remotepath}")
        except Exception as e:
            self.logger.error(e)


def export_list(self, listname, purge_file=False):
    '''
    Google prefers all excel files to have an xlsx extension
    :param listname: student, judge, or volunteer
    :param purge_file: delete local file when done, default: false
    :return:
    '''
    if self.token is None:
        raise ValueError('no token found in object, login before calling export_student_list')
    # self.set_columns(listname)
    payload = {'_token': self.token,
               'filetype': 'xls',
               'orderby1': '',
               'sortby1': '',
               'searchhere1': ''
               }
    if listname == 'student':
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
        url = f'{self.url_base}/fairadmin/exportVolunteerExcelPdf'
        payload_specific = {
            'searchhere1': '',
            'registration_status1': '',
            'last_year': '',
        }
    elif listname == 'paymentStatus':
        url = f'{self.url_base}/fairadmin/paymentStatus'
        payload_specific = {
            'management_user_type_id1': '8',
            'student_checkin_status1': '',
            'admin_status1': '',
            'payment_type1': '',
            'division1': '0',
            'number_page': '',
            'page1': '',
            'child_fair_select1': '',
            'origin_fair_select1': '',
            'teacher_id1': '',
            'student_completion_status1': '',
            'final_status1': '',
            'files_approval_status1': '',
            'project_status1': '',
            'checked_fields': '',
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

    remotepath = f'/Automation/{self.domain}/{listname} list.xlsx'
    if df.shape[0] > 0:
        self.googleapi.create_file(filename_local, remotepath)
    else:
        self.logger.info(f"{listname} list is empty, skipping upload to Google")
    if purge_file:
        try:
            os.remove(filename_local)
        except OSError as e:
            print(f'failed to remove {filename_local} {e}')
    return (filename_local, df)


def download_files_locally(self, studentid, filedata):
    student_local_dir = f"{self.parent_file_dir}/{self.region_domain}/{studentid}"
    documenttypes = filedata.keys()
    for documenttype in documenttypes:
        download = None
        try:
            if filedata[documenttype]['file_name'] == 'NONE':
                continue
        except Exception as e:
            print(e)
            pprint(filedata[documenttype])
            raise
        atoms = filedata[documenttype]['file_name'].split('.')
        documenttypefortilename = simplify_filenames(documenttype)
        local_filename = f"{documenttypefortilename}.{atoms[-1]}"
        local_full_path = f"{student_local_dir}/{local_filename}"
        filedata[documenttype]['local_filename'] = local_filename
        filedata[documenttype]['local_full_path'] = local_full_path
        # this_file_data['local_full_path'] = local_full_path
        if os.path.exists(local_full_path):
            localmtime = datetime.fromtimestamp(os.path.getmtime(local_full_path))
            filedata[documenttype]['local_mtime'] = localmtime
            try:
                if type(filedata[documenttype]['updated_on']) is str:
                    # when cached, datetimes are serialized to strings
                    filedata[documenttype]['updated_on'] = parser.parse(filedata[documenttype]['updated_on'])
                download = filedata[documenttype]['updated_on'] is None or localmtime < filedata[documenttype][
                    'updated_on']
            except Exception as e:
                print(e)
                pprint(filedata[documenttype])
                raise
        else:
            download = True
        download = download and filedata[documenttype]['file_status'] in ['SUBMITTED', 'APPROVED']
        dld = os.path.isfile(local_full_path)
        download = download and not os.path.isfile(local_full_path)
        if download:
            if filedata[documenttype]['file_name'] is None or len(filedata[documenttype]['file_name']) < 5:
                self.logger.debug(f"{documenttype} not uploaded yet by student {studentid}")
                continue
            if filedata[documenttype]['uploaded_file_name'] is not None:
                thatdata = filedata[documenttype]
                full_pathname, used_cache = self.DownloadFileFromSTEMWizard(filedata[documenttype]['file_name'],
                                                                            filedata[documenttype][
                                                                                'uploaded_file_name'],
                                                                            f"{studentid}", local_filename)
            elif filedata[documenttype]['uploaded_file_name'] is None:
                full_pathname, used_cache = self.DownloadFileFromS3Bucket(filedata[documenttype]['file_url'],
                                                                          f"{studentid}", local_filename)
            else:
                self.logger.error(f"could not determine download for student {studentid} {documenttype}")
            if os.path.exists(local_full_path):
                localmtime = datetime.fromtimestamp(os.path.getmtime(local_full_path))
                filedata[documenttype]['local_mtime'] = localmtime
            else:
                filedata[documenttype]['local_mtime'] = None
        elif os.path.isfile(local_full_path):
            self.logger.info(f"skipping {local_full_path}")

    return filedata


def simplify_filenames(documenttype):
    documenttypefortilename = documenttype
    if 'plan' in documenttypefortilename.lower():
        documenttypefortilename = 'Research Plan'
    if 'abstract' in documenttypefortilename.lower():
        documenttypefortilename = 'Abstract'
    documenttypefortilename = documenttypefortilename.replace('2022_NCSEF_', '')
    documenttypefortilename = documenttypefortilename.replace('2022 NCSEF ', '')
    documenttypefortilename = documenttypefortilename.replace('Form_', '')
    documenttypefortilename = documenttypefortilename.replace(' Form', '')
    documenttypefortilename = documenttypefortilename.replace('FORM', '')
    documenttypefortilename = documenttypefortilename.replace('Science Fair -', '')
    return documenttypefortilename


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
