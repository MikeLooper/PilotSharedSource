cd C:\Working\Storage\Dev\GitHub

cd PilotApiDotNet
git submodule update --remote --recursive shared/PilotSharedSource
git add shared/PilotSharedSource
cd ..

cd PilotApiJava
git submodule update --remote --recursive shared/PilotSharedSource
git add shared/PilotSharedSource
cd ..

cd PilotApiPython
git submodule update --remote --recursive shared/PilotSharedSource
git add shared/PilotSharedSource
cd ..

cd PilotMcpServer
git submodule update --remote --recursive shared/PilotSharedSource
git add shared/PilotSharedSource
cd ..

cd PilotUiAngular
git submodule update --remote --recursive shared/PilotSharedSource
git add shared/PilotSharedSource
cd ..
