from gspread_pandas import Spread, Client, conf
from gspread.exceptions import SpreadsheetNotFound
from openpyxl.styles import Alignment, Font
from STEMWizard.logstuff import get_logger
from pprint import pprint
from pydrive2.auth import GoogleAuth, ServiceAccountCredentials
from pydrive2.drive import GoogleDrive
from googleapiclient.discovery import build
from dateutil import parser
from datetime import datetime, timedelta, timezone

import json

logger = get_logger('google')


class NCSEFGoogleDrive(object):
    FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
    common_mime_types = {'pdf': 'application/pdf',
                         'zip': 'application/zip',
                         'avi': 'video/x-msvideo',
                         'xls': 'application/vnd.ms-excel',
                         'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         'csv': 'text/csv',
                         'gif': 'image/gif',
                         'jpg': 'image/jpeg',
                         'jpeg': 'image/jpeg',
                         'png': 'image/png',
                         'tif': 'image/tiff',
                         'txt': 'text/plain',
                         'tiff': 'image/tiff',
                         'mp3': 'audio/mpeg',
                         'wav': 'audio/wav',
                         'mov': 'video/mov',
                         'doc': 'application/msword',
                         'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                         'rtf': 'application/rtf',
                         'ppt': 'application/vnd.ms-powerpoint',
                         'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',

                         }

    def __init__(self):
        self.drive = self._auth()
        self.ids = None
        self.last_updated = None
        self.last_checked = None
        self.list_all()

    def __str__(self, root=None):
        indent = 0
        response = ""
        for id, node in self.ids.items():
            if node['labels']['trashed']:
                continue
            elif root is not None:
                if node['fullpath'] == root:
                    response += self._node_output(node, root=root)
            elif len(node['parents']) == 0:
                response += self._node_output(node)
        return response

    def dump(self, root):
        return(self.__str__(root=root))

    def _auth(self):
        gauth = GoogleAuth()
        scope = ['https://www.googleapis.com/auth/drive']
        gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name('client_secrets.json', scope)
        drive = GoogleDrive(gauth)
        return drive

    def _node_output(self, node, indent=0, root=None):
        response=''
        if root is None or node['fullpath'].startswith(root):
            mt = ''
            if 'folder' in node['mimeType']:
                emoji = '📁'
            elif 'zip' in node['mimeType'] or 'tar' in node['mimeType']:
                emoji = '🗜️'
            elif 'image' in node['mimeType']:
                emoji = '🖼️'
            elif 'pdf' in node['mimeType']:
                emoji = '🅿️'
            elif 'sheet' in node['mimeType']:
                emoji = '🔢'
            elif 'text' in node['mimeType']:
                emoji = '📄'
            else:
                emoji = '📄'
                mt = node['mimeType']
            response = (f"{'.' * indent}{emoji}{node['fullpath']}\n")
            for child in set(node['children']):
                response += self._node_output(self.ids[child], indent=indent + 1)
        return response

    def _buildpath(self, node, path):
        node['fullpath'] = f"{path}/{node['title']}"
        for child in set(node['children']):
            if child in self.ids.keys():
                self._buildpath(self.ids[child], node['fullpath'])
            else:
                raise ValueError(f"{child} id not found under {node['title']}")

    def _write_cache(self):
        fp = open('GoogleDriveCache.json', 'w')
        json.dump({'ids': self.ids,
                   'last_updated': self.last_updated,
                   'last_checked': self.last_checked}, fp, indent=2)
        fp.close()

    def list_all(self, id=None, cache_checked_ttl=300, cache_update_ttl=21600):
        try:
            fp = open('GoogleDriveCache.json', 'r')
            cache = json.loads(fp.read())
            fp.close()
            cache_by_id = cache['ids']
            last_updated = cache['last_updated']
            last_checked = cache['last_checked']
        except Exception as e:
            print(f'error {e}')
            cache_by_id = {}
            cache_by_tree = {}
            last_updated = '1970-01-01T00:00:00.000Z'
            last_checked = '1970-01-01T00:00:00.000Z'
        utcnow = datetime.utcnow().replace(tzinfo=timezone.utc)
        checked_delta = utcnow - parser.isoparse(last_checked)
        updated_delta = utcnow - parser.isoparse(last_updated)

        if checked_delta.total_seconds() > cache_checked_ttl:  # or updated_delta.total_seconds() > cache_update_ttl:
            logger.info(f'refetching file info, last checked {checked_delta.total_seconds() / 60:.1f} minutes ago')
            last_checked = utcnow.isoformat()
            for file_list in self.drive.ListFile({'q': 'trashed=false', 'maxResults': 500}):
                for fileinfo in file_list:
                    if fileinfo['mimeType'] == NCSEFGoogleDrive.FOLDER_MIME_TYPE:
                        pass
                    elif 'shortcut' in fileinfo['mimeType']:
                        continue
                    cache_by_id[fileinfo['id']] = fileinfo
                    cache_by_id[fileinfo['id']]['children'] = []
                    cache_by_id[fileinfo['id']]['fullpath'] = ''
        else:
            logger.debug(f'using cached file info, last checked {checked_delta.total_seconds() / 60:.1f} minutes ago')

        for id, data in cache_by_id.items():
            if data['modifiedDate'] > last_updated:
                last_updated = data['modifiedDate']

            for parent in data['parents']:
                if parent['id'] not in cache_by_id.keys():
                    continue  # likely in trash
                cache_by_id[parent['id']]['children'].append(id)

        self.ids = cache_by_id
        self.last_updated = last_updated
        self.last_checked = last_checked

        for id, data in cache_by_id.items():
            if len(data['parents']) == 0:
                self._buildpath(data, '')

        self._write_cache()

    def create_file(self, localpath, remotepath, mimeType='application/vnd.google-apps.file'):
        found, found_folder, parentid, parentpath, title = self._find_file(remotepath)
        if not found:
            if parentid is None:
                parentitem = self.create_folder(parentpath)
                parentid = parentitem['id']

            for ext, mtype in NCSEFGoogleDrive.common_mime_types.items():
                if localpath.endswith(f'.{ext}'):
                    mimeType = mtype
            item = self.drive.CreateFile(
                {"title": title, "parents": [{"id": parentid}],
                 "mimeType": mimeType}
            )
            item.SetContentFile(localpath)
            item.Upload()
        else:
            logger.error(f'{remotepath} already exists')

    def create_folder(self, fullpath, expectedroot='Automation', refresh=True):
        item = {}
        found, found_folder, parentid, parentpath, title = self._find_file(fullpath)
        if found and found_folder:
            logger.warning(f"folder {fullpath} already exists")
        elif found and not found_folder:
            logger.error(f"{fullpath} already exists as a non-folder")
        else:
            if parentid is None:
                raise ValueError(f'parent folder {parentpath} not found')
            item = self.drive.CreateFile(
                {"title": title, "parents": [{"id": parentid}],
                 "mimeType": NCSEFGoogleDrive.FOLDER_MIME_TYPE}
            )
            item.Upload()

            # update local cache
            item['fullpath'] = fullpath
            item['children'] = []
            self.ids[item['id']] = item
            self._write_cache()

            parentid = item['id']
            logger.info(f"created {title} in {parentpath} {item['id']}")

            if refresh:
                self.list_all(cache_update_ttl=0)
        return item

    def _find_file(self, fullpath):
        found = False
        found_folder = False
        elements = fullpath.split('/')
        parentpath = '/'.join(elements[:-1])
        title = elements[-1]
        parentid = None
        for id, data in self.ids.items():
            if data['fullpath'] == parentpath:
                parentid = id
            if data['fullpath'] == fullpath:
                found = True
                if data['mimeType'] == NCSEFGoogleDrive.FOLDER_MIME_TYPE:
                    found_folder = True
        return found, found_folder, parentid, parentpath, title


def get_sheet(sheetname):
    config = conf.get_config(conf_dir='.', file_name='google_secret.json')

    logger.info(f'fetching {sheetname} from Google')
    try:
        spread = Spread(sheetname, config=config)
        df = spread.sheet_to_df(index=None)
        perm = spread.list_permissions()
        pprint(perm)
        print(df)
        spread.move('/')


    except SpreadsheetNotFound as e:
        logger.error(
            f"{e} {sheetname}, ensure that the sheet is shared with")
        raise
