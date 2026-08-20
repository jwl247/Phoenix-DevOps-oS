
# First, finish fixing SSH keys
ssh-keygen -R 192.168.1.108
ssh-copy-id jwl247@192.168.1.108

# Copy everything over
scp universal_kernel.c jwl247@192.168.1.108:~/
scp encompass_kernel_config.json jwl247@192.168.1.108:~/
scp encompass_syncthing.py jwl247@192.168.1.108:~/

# SSH in
ssh jwl247@192.168.1.108

# Install deps
sudo dnf install python3-devel gcc syncthing python3-requests -y

# Compile ENCOMPASS
gcc -o ENCOMPASS ENCOMPASS.c \
    -lpython3.9 -lm \
    -I/usr/include/python3.9

# Test Syncthing module standalone
python3 encompass_syncthing.py test

# Run the full kernel!
./encompass encompass_kernel_config.json

cd /etc/HEix7_3GIII

gcc -o ENCOMPASS ENCOMPASS.c \
    -lpython3.9 -lm \
    -I/usr/include/python3.9

