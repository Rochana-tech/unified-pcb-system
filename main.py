"""One entry point for UI, API and all integrated manufacturing layers."""
import argparse
import os
from pathlib import Path
import uvicorn
from integration.config import Settings
from integration.api import create_app

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['demo','external'],default='demo')
    parser.add_argument('--port',type=int,default=int(os.getenv('PORT','8002')))
    parser.add_argument('--host',default=os.getenv('HOST','127.0.0.1'))
    parser.add_argument('--correction-seconds',type=int,default=20)
    parser.add_argument('--no-demo-backup',action='store_true')
    parser.add_argument('--mqtt',action='store_true')
    parser.add_argument('--database',default=os.getenv('DATABASE_PATH',str(Path(__file__).parent/'data/manufacturing.sqlite3')))
    args=parser.parse_args()
    if args.correction_seconds<1 or args.correction_seconds>3600:
        parser.error('correction-seconds must be 1..3600')
    if args.mqtt and args.mode!='external':
        parser.error('--mqtt requires --mode external')
    settings=Settings(args.mode,args.database,args.correction_seconds,not args.no_demo_backup,
        public_site=os.getenv('PUBLIC_DEPLOYMENT','0')=='1',operator_key=os.getenv('OPERATOR_KEY',''))
    print('Dashboard: http://127.0.0.1:'+str(args.port))
    print('Demo uses generated data. External mode starts empty and waits for telemetry.')
    uvicorn.run(create_app(settings,mqtt_enabled=args.mqtt),host=args.host,port=args.port,workers=1)

if __name__=='__main__':
    main()

