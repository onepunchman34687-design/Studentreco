# USB Portable Attendance App

## Setup
1. On a 64-bit Windows 10/11 computer, connect the USB drive and ensure several GB of free space and internet access.
2. Double-click `prepare_portable_python.bat` and wait until it explicitly says `SETUP COMPLETE`.
3. Start the app with `start_attendance.bat`.

The setup installs Python 3.11.9 under `python\`, installs dependencies with that interpreter, and stores the InsightFace model under `insightface_data\`. The launcher explicitly uses `python\python.exe`, not the computer's system Python. App data is intended to stay in this project folder.

## InsightFace installation note
The upstream `insightface==0.7.3` source distribution can require Microsoft C++ Build Tools on Windows. To avoid compiling it locally, this setup downloads a prebuilt Python 3.11 x64 wheel from the community repository `Gourieff/Assets` and installs it without dependency resolution; the dependencies needed for this app are listed in `requirements.txt`. This is an unofficial third-party wheel, not an official InsightFace release. Use only if you are comfortable trusting that source. Internet access is required during setup. If the download is blocked or the wheel changes, setup stops and reports failure.

## Important portability limits
This folder does not include the Python runtime or AI model in the ZIP; the setup downloads them. The completed folder should be tested on another compatible 64-bit Windows PC before classroom use. Camera permissions, Windows native runtimes, USB speed, and PC security policies can vary. Keep biometric/student data private and do not unplug the drive while the app is running.
