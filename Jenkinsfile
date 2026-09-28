pipeline { agent any; stages {
stage('Install'){steps{sh 'pip install -r requirements.txt'}}
stage('Test'){steps{sh 'pytest -q'}}
stage('Build'){steps{sh 'docker build -t smart-canteen .'}}
} }
