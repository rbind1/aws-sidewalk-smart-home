import boto3
import zipfile
import io

code = open('lambda/uplink_decoder/index.py').read()

old = 'temp_raw, hum_raw, flags, seq = struct.unpack'

new = '    print("Raw hex:", raw.hex())\n    print("Raw bytes:", list(raw))\n    ' + old

code = code.replace(old, new)

buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w') as z:
    z.writestr('index.py', code)

boto3.client('lambda', region_name='us-east-1').update_function_code(
    FunctionName='SidewalkUplinkDecoder',
    ZipFile=buf.getvalue()
)
print('Lambda updated with debug logging')