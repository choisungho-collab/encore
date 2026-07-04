name: Build Windows EXE

on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build:
    runs-on: windows-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pyinstaller

      - name: Build single EXE
        run: >
          pyinstaller --onefile --windowed --name sc_recorder --noupx
          --icon icon.ico
          --version-file version_info.txt
          --add-data "web;web"
          --hidden-import psutil --hidden-import requests --hidden-import tkinter
          --hidden-import pyaudiowpatch
          --exclude-module boto3 --exclude-module botocore --exclude-module numpy
          --exclude-module windows_capture
          --exclude-module flask --exclude-module werkzeug --exclude-module jinja2
          --exclude-module waitress
          --exclude-module cv2 --exclude-module opencv-python --exclude-module matplotlib
          sc_recorder.py

      - name: Zip the EXE (브라우저의 .exe 다운로드 차단 회피용 .zip)
        shell: pwsh
        run: |
          Compress-Archive -Path dist/sc_recorder.exe -DestinationPath dist/sc_recorder.zip -Force
          if (-not (Test-Path dist/sc_recorder.zip)) { throw "sc_recorder.zip 생성 실패" }
          Get-ChildItem dist | Format-Table Name, Length

      - name: Upload artifact (zip)
        uses: actions/upload-artifact@v4
        with:
          name: sc_recorder-windows
          path: dist/sc_recorder.zip

      - name: Publish "latest" release (push to main)
        if: github.ref == 'refs/heads/main'
        uses: softprops/action-gh-release@v2
        with:
          tag_name: latest
          name: Latest build
          body: |
            Download sc_recorder.zip, unzip it, and run sc_recorder.exe - no Python needed.
            If Windows SmartScreen warns, click "More info -> Run anyway". On first launch it downloads the video tool (ffmpeg) once (1-2 min).
          files: |
            dist/sc_recorder.zip
            dist/sc_recorder.exe
          make_latest: true

      - name: Publish release (version tag)
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          body: |
            Download sc_recorder.zip, unzip it, and run sc_recorder.exe - no Python needed.
            If Windows SmartScreen warns, click "More info -> Run anyway". On first launch it downloads the video tool (ffmpeg) once (1-2 min).
          files: |
            dist/sc_recorder.zip
            dist/sc_recorder.exe
