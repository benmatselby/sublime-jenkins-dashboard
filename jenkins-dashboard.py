import json
import base64
import threading
import sys
import os
import urllib
import sublime
import sublime_plugin

class Pref:

    keys = [
        "show_debug",
        "jenkins_url",
        "username",
        "password",
    ]

    def load(self):
        self.settings = sublime.load_settings('jenkins-dashboard.sublime-settings')

        if sublime.active_window() is not None:
            project_settings = sublime.active_window().active_view().settings()
            if project_settings.has("jenkins-dashboard"):
                project_settings.clear_on_change('jenkins-dashboard')
                self.project_settings = project_settings.get('jenkins-dashboard')
                project_settings.add_on_change('jenkins-dashboard', pref.load)
            else:
                self.project_settings = {}
        else:
            self.project_settings = {}

        for key in self.keys:
            self.settings.clear_on_change(key)
            setattr(self, key, self.get_setting(key))
            self.settings.add_on_change(key, pref.load)

    def get_setting(self, key):
        if key in self.project_settings:
            return self.project_settings.get(key)
        else:
            return self.settings.get(key)

pref = Pref()

def plugin_loaded():
    pref.load()

def debug_message(msg):
    if pref.show_debug == True:
        print("[jenkins-dashboard] " + str(msg))


class Jenkins():
    """Jenkins Controller class"""
    def __init__(self):
        if pref.username and pref.password:
            self.auth = self.auth_headers(pref.username, pref.password)
        else :
            self.auth = None

    def auth_headers(self, username, password):
        '''Simple implementation of HTTP Basic Authentication.
        Returns the 'Authentication' header value.
        '''
        auth = '%s:%s' % (username, password)
        auth = auth.encode('utf-8')
        return b'Basic ' + base64.b64encode(auth)

    def get_response(self, uri):
        jenkins_url = pref.jenkins_url + uri
        debug_message("GET: " + jenkins_url)

        req = urllib.request.Request(jenkins_url)
        data = urllib.parse.urlencode({'token': 1}) # Config needed here
        data = data.encode('utf-8')

        if self.auth :
            req.add_header('Authorization', self.auth)

        response = urllib.request.urlopen(req, data)

        return response

    def get_dashboard(self):
        build_report = []
        try:
            response = self.get_response("/api/json")

            jenkins_dashboard = response.read().decode('utf-8')
            debug_message(jenkins_dashboard)
        except urllib.error.URLError as e:
            debug_message("HTTP Error: " + str(e.code))
            if e.code == 403:
                return [['Error', str(e.code) + ' Authentication required']]
            return [['Error', str(e.code)]]

        try:
            dashboard_json = json.loads(jenkins_dashboard)
        except:
            debug_message("Unable to parse the Jenkins json response")
            return build_report

        for job in dashboard_json['jobs']:
            if job['color'] == 'blue':
                build_report.append([job['name'], 'SUCCESS'])
            elif job['color'] == 'blue_anime':
                build_report.append([job['name'], 'SUCCESS - BUILDING'])
            elif job['color'] == 'yellow':
                build_report.append([job['name'], 'UNSTABLE'])
            elif job['color'] == 'yellow_anime':
                build_report.append([job['name'], 'UNSTABLE - BUILDING'])
            elif job['color'] == 'red':
                build_report.append([job['name'], 'FAILURE'])
            elif job['color'] == 'red_anime':
                build_report.append([job['name'], 'FAILURE - BUILDING'])
            elif job['color'] == 'aborted':
                build_report.append([job['name'], 'ABORTED'])
            elif job['color'] == 'aborted_anime':
                build_report.append([job['name'], 'ABORTED - BUILDING'])
            elif job['color'] == 'disabled':
                build_report.append([job['name'], 'DISABLED'])
            elif job['color'] == 'notbuilt':
                build_report.append([job['name'], 'NO BUILDS'])
            else:
                build_report.append([job['name'], 'UNKNOWN'])

        return build_report

    def build_job(self, jobName):
        try:
            response = self.get_response("/job/" + jobName + "/build")
            debug_message("HTTP Status Code: " + str(response.status))
            return True
        except urllib.error.URLError as e:
            debug_message("HTTP Status Code: " + str(e.code) + "\nHTTP Status Reason: " + e.reason)
            return False

    def get_job_report(self, jobName):
        try:
            response = self.get_response("/job/" + jobName + "/api/json")
            data = json.loads(response.read().decode('utf-8'))
            return data
        except urllib.error.URLError as e:
            return str(e.reason)

    def get_last_job(self, jobName):
        try:
            response = self.get_response("/job/" + jobName + "/lastBuild/api/json")
            data = json.loads(response.read().decode('utf-8'))
            return data
        except urllib.error.URLError as e:
            return "HTTP Status Code: " + str(e.code) + "\nHTTP Status Reason: " + e.reason


    def get_last_output(self, jobName):
        try:
            response = self.get_response("/job/" + jobName + "/lastBuild/consoleText")
            data = str(response.read().decode('utf-8'))
            return data
        except urllib.error.URLError as e:
            return "HTTP Status Code: " + str(e.code) + "\nHTTP Status Reason: " + e.reason



class BaseJenkinsDashboardCommand(sublime_plugin.TextCommand):
    """Base command class for Jenkins Dashboard"""
    description = ''

    def run(self, args):
        debug_message('Not implemented')

    def show_quick_panel(self, data):
        self.view.window().show_quick_panel(data, self.on_quick_panel_done)

    def on_quick_panel_done(self, picked):
        debug_message('Not implemented')
        return

    def render_jenkins_information(self, output):
        view = self.view.window().new_file()
        view.run_command('clear')
        content = 'Job: ' +  output.get('name') + '\n\n'
        content += json.dumps(output, indent=4, separators=(',', ': '))

        view.run_command('output', {'console_output': content})


class ShowJenkinsDashboardCommand(BaseJenkinsDashboardCommand):
    """Show the Jenkins Dashboard"""
    description = 'Show Jenkins Dashboard ...'
    build_report = []

    def is_enabled(self):
        if pref.jenkins_url != "":
            return True
        else:
            return False

    def run(self, args):
        cmd = Jenkins()
        self.build_report = cmd.get_dashboard()
        self.show_quick_panel(self.build_report)

    def on_quick_panel_done(self, picked):
        if picked == -1:
            return

        job = self.build_report[picked][0]
        cmd = Jenkins()
        job_report = cmd.get_job_report(job)
        debug_message(job_report);
        self.render_jenkins_information(job_report)
        return


class BuildJenkinsJobCommand(BaseJenkinsDashboardCommand):
    """Show Jenkins Jobs and then build the one selected"""
    description = 'Build Jenkins Job ...'

    def is_enabled(self):
        if pref.jenkins_url != "":
            return True
        else:
            return False

    def run(self, args):
        cmd = Jenkins()
        self.build_report = cmd.get_dashboard()
        self.show_quick_panel(self.build_report)

    def on_quick_panel_done(self, p):
        if p == -1:
            return

        cmd = Jenkins()
        picked = self.build_report[p][0]

        if picked == 'Error':
            debug_message(picked)
            return

        prevJob = cmd.get_last_job(picked) # to check if new job was started
        is_building = cmd.build_job(picked)

        view = self.view.window().new_file()
        if is_building:
            self.numberOfTries = 20
            self.output(view, cmd, picked, prevJob.get('number'))
        else:
            view.run_command('output', {'console_output': 'Something went wrong, you can debug it with setting "show_debug" to true'})
        return

    def output(self, view, cmd, picked, prevJobNumber=None, **args):
        job = cmd.get_last_job(picked)
        if job.get('number') == prevJobNumber:
            # job don't start yet
            view.run_command('clear')
            if not hasattr(self, 'dots') or self.dots == '...':
                self.dots = ''
            self.dots += '.'
            view.run_command('output', {'console_output': 'Waiting for the job to build' + self.dots})
            self.numberOfTries -= 1
            if self.numberOfTries == 0:
                view.run_command('clear')
                view.run_command('output', {'console_output': 'Something went wrong, the job cannot start'})
                return
            threading.Timer(1, self.output, [view, cmd, picked, prevJobNumber]).start()

            return

        if prevJobNumber:
            view.run_command('clear')

        console_output = cmd.get_last_output(picked)
        content = 'Job: ' + job.get('fullDisplayName') + '\n\n' + console_output

        debug_message(job.get('fullDisplayName') + " build status: " + str(job.get('building')) + "\n")

        if job.get('building'):
            threading.Timer(1, self.output, [view, cmd, picked]).start()
        else:
            content = content + '\n\nDone with ' + job.get('result')

        view.run_command('output', {'console_output': content})

class OutputCommand(sublime_plugin.TextCommand):
    def run(self, edit, **args):
        sizeBefore = self.view.size()
        self.view.insert(edit, sizeBefore, args.get('console_output')[sizeBefore:])
        self.view.show(self.view.size())

class ClearCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        sizeBefore = self.view.size()
        self.view.erase(edit, sublime.Region(0, sizeBefore))
