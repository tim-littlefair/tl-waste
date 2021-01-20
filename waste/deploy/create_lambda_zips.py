import time
import os
import subprocess
import sys
import zipfile

PACKAGE_LIST = [
    'requests',
    # 'grequests',
    'piexif',
]

run_id = int(time.time())
layer_run_dir = "trailer_layer_%d" % (run_id,)
layer_run_zip = layer_run_dir + ".zip"
handler_run_zip = "trailer_handler_%d.zip" % (run_id,)

os.umask(0o022)

os.mkdir(layer_run_dir)
for package in PACKAGE_LIST:
    subprocess.check_call([
            sys.executable, "-m", "pip", "install", package,'-t',layer_run_dir
    ])
layer_zip = zipfile.ZipFile(layer_run_zip, mode='w')
for dirpath,_,files in os.walk(layer_run_dir,topdown=True):
    for f in files:
        relpath = os.path.join(dirpath,f)
        zippath = relpath.replace(layer_run_dir,"python")
        zinfo = zipfile.ZipInfo(zippath)
        zinfo.external_attr = 0o755 << 16 # file permissions rwxr_xr_x
        layer_zip.writestr(zinfo, open(relpath,'rb').read())
layer_zip.close()

handler_zip = zipfile.ZipFile(handler_run_zip, mode='w')
for f in ('lambda_handler', 'simple_lambda_handler'):
    zinfo = zipfile.ZipInfo(f+".py")
    zinfo.external_attr = 0o755 << 16 # file permissions rwxr_xr_x
    fpath = "deploy/" + f + ".py"
    handler_zip.writestr(zinfo, open(fpath,'rb').read())
for d in ('serialization', 'url_to_trail'):
    for f in os.listdir(d):
        if f in "__pycache__":
            continue
        fpath = d + "/" + f
        zinfo = zipfile.ZipInfo( fpath )
        zinfo.external_attr = 0o755 << 16 # file permissions rwxr_xr_x
        handler_zip.writestr(zinfo, open(fpath,'rb').read())
handler_zip.close()

print(handler_run_zip,layer_run_zip)

