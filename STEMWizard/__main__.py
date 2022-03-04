from . import STEMWizardAPI
if __name__ == '__main__':
    configfile_prod = 'stemwizardapi_ncsef.yaml'
    uut = STEMWizardAPI(configfile=configfile_prod, login_stemwizard=True, login_google=True)
    student_data = uut.studentSync()