from io import TextIOWrapper
import os
from subprocess import Popen, PIPE, TimeoutExpired
from typing import Optional, List, Dict
import re
import logging
import pathlib
import json
from collections import defaultdict

from rhubarb_lipsync.rhubarb.mouth_shape_data import MouthCue

log = logging.getLogger(__name__)

class RhubarbParser:

    version_info_rx=re.compile(r"version\s+(?P<ver>\d+\.\d+\.\d+)")

    LOG_LEVELS_MAP =defaultdict(lambda:logging.DEBUG)
    LOG_LEVELS_MAP.update({
        "Fatal" : logging.CRITICAL, #TODO Verify
        "Error" : logging.ERROR,
        "Info" : logging.INFO,
    })
    
    @staticmethod
    def parse_version_info(stdout:str)->str:
        m=re.search(RhubarbParser.version_info_rx, stdout)
        if m is None: return ""
        return m.groupdict()["ver"]

    @staticmethod
    def parse_status_infos(stderr:str)->Dict[str, Dict]:
        """Parses the one-line json(s) produced by rhubarb binary. 
        Each report is a json on separate line"""
        if not stderr: return {}     
        return [RhubarbParser.parse_status_info_line(l) for l in stderr.splitlines()]

    @staticmethod
    def parse_status_info_line(stderr_line:str)->Dict:
        if not stderr_line: return {}
        try:
            
            return json.loads(stderr_line)
            # { "type":"start", "file":"1.ogg", "log":{"level":"Info","message": "Application startup." } }
            # { "type": "failure", "reason": ...
            # { "type": "progress", "value": 0.17, 
        except json.JSONDecodeError:
            log.exception(f"Failed to parse status line '{stderr_line[:100]}'")
            return {}
        

    @staticmethod
    def parse_lipsync_json(stdout:str)->List[Dict]:
        """Parses the main lipsync output json. Return only the list of mouthCues"""
        # { "metadata": { "soundFile": "1.ogg", "duration": 5.68},  
        #   "mouthCues": [ { "start": 0.00, "end": 0.28, "value": "X" } ... ] }

        if not stdout: return {}
        try:
            j = json.loads(stdout)
            return j["mouthCues"]
        except json.JSONDecodeError:
            log.exception(f"Failed to parse main rhubarb output json. '{stdout[:200]}...'")
            return {}

    @staticmethod
    def lipsync_json2MouthCues(cues_json:List[Dict])->List[MouthCue]:
        return [MouthCue.of_json(c_json) for c_json in cues_json]

    

class RhubarbCommandWrapper:
    """Wraps low level operations related to the lipsync executable."""

    def __init__(self, executable_path:pathlib.Path, recognizer="pocketSphinx", extra_args=[]):
        self.executable_path = executable_path
        self.recognizer = recognizer        
        self.process:Optional[Popen]=None
        self.stdout=""
        self.stderr=""
        self.last_exit_code:Optional[int]=None
        self.extra_args=extra_args

  
    def errors(self) -> Optional[str]:
        if not self.executable_path:
            return "Configure the Rhubarb lipsync executable file path in the addon preferences. "
         
        
        if not self.executable_path.exists():
            return f"The '{self.executable_path}' doesn't exist."
        if not self.executable_path.is_file():
            return f"The '{self.executable_path}' is not a valid file."
        # Zip doesn't maintain file flags, set as executable    
        os.chmod(self.executable_path, 0o744)
        return None

    def build_lipsync_args(self, input_file: str, dialog_file: Optional[str] = None):
        dialog = ["--dialogFile", dialog_file] if dialog_file else []
        return [self.executable_path,
                "-f", "json", 
                "--machineReadable", 
                "--extendedShapes", "GHX",
                "-r", self.recognizer,
                *dialog,
                input_file]

    def build_version_args(self):
        return [self.executable_path, "--version"]

    def open_process(self, cmd_args:List[str]):
        assert not self.was_started
        assert not self.errors(),  self.errors()
        self.stdout=""
        self.stderr=""
        self.last_exit_code=None
        # universal_newlines forces text mode
        self.process = Popen(self.extra_args + cmd_args, stdout=PIPE, stderr=PIPE, universal_newlines=True)

    def close_process(self):
        if self.was_started:
            self.process.terminate()        
        self.process=None

    def get_version(self)->str:
        """Execute `lipsync --version` to get the current version of the binary. Synchroinous call."""
        self.close_process()
        args = self.build_version_args()
        self.open_process(args)
        self.collect_output_sync(ignore_timeout_error=False)
        return RhubarbParser.parse_version_info(self.stdout)

    def log_status_line(self, log_json:dict):
        # {'log': {'level': 'Info', 'message': 'Msg'}}]
        if not log_json or not 'log' in log_json.keys():            
            return #Not log key included in the progress line
        level = log_json["log"]["level"]
        msg = log_json["log"]["message"]

        log.log(RhubarbParser.LOG_LEVELS_MAP[level], f"Rhubarb: {msg}")
    
    


    def lipsync_start(self, input_file: str, dialog_file: Optional[str] = None):
        """Start the main lipsync command. Process runs in background"""
        self.close_process()
        args = self.build_lipsync_args(input_file, dialog_file)
        log.info(f"Starting lipsync:\n{args}")
        self.open_process(args)

    def lipsync_check_progress(self)->int|None:
        """Reads the stderr of the lipsync command where the progress and status in being reported"""
        assert self.was_started
        self.stderr=""
        self.read_process_stderr_line()
        if not self.stderr:
            return None
        status_lines = RhubarbParser.parse_status_infos(self.stderr)
        if not status_lines:
            return None
        for s in status_lines: 
            self.log_status_line(s)
        by_type={j["type"]:j for j in status_lines if j}
        if "failure" in by_type.keys():
            raise RuntimeError(f"Rhubarb binary failed:\n{by_type['failure']['reason']}")
        if not "progress" in by_type.keys():        
            return None
        v=by_type["progress"]["value"]
        return int(v*100)
        

        

    @property
    def was_started(self)->bool:
        """Whether the process has been triggered already. Might be still running running or have finished"""
        return self.process is not None

    @property
    def has_finished(self)->bool:
        """
        Whether the process has finished. Either sucessfully or with an error.
        When True the process is not running and the last_out and the last_error are complete
        """
        #if not self.was_started: 
        #    return False
        return self.last_exit_code is not None

    def collect_output_sync(self, ignore_timeout_error=True, timeout=1):
        """
        Waits (with a timeout) for the process to finish. Then collects its std out and std error
        """
        assert self.was_started
        try: 
            (stdout, stderr) = self.process.communicate(timeout=1) # Consume any reminding output 
            self.stderr+=stderr
            self.stdout+=stdout
        except TimeoutExpired as ex:
            log.warn(f"Timed out while waiting for process to finalize outputs")
            if not ignore_timeout_error: 
                raise
        self.close_process()

    
    def read_process_stderr_line(self):
        assert self.was_started
        if self.has_finished:
            return

        #(stdout, stderr) = self.process.communicate(timeout=timeout)
        self.last_exit_code = self.process.poll()
        if self.last_exit_code is not None: # Process has finished
            # Collect the output just in case
            self.collect_output_sync(ignore_timeout_error=True)
            if self.last_exit_code !=0:
                raise RuntimeError(f"Rhubarb binary exited with a non-zero exit code")
            return
        
        try: 
            # Rhubarb binary is reporting progress on the stderr. Read next line.
            # This would eventually block. But as rhubarb is reporting the progress every few seconds 
            # the GUI freezing should be reasonable
            n = next(self.process.stderr) # type: ignore
            self.stderr+= n
        except StopIteration:
            log.debug(f"EOF reached while reading the stderr") # Process has just terminated