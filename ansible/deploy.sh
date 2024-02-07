#!/bin/bash

ansible-playbook -i ./hosts ./server.yaml
ansible-playbook -i ./hosts ./ssh_key_repo.yaml
# Prompt the user to copy and paste the public key to their GitHub account
read -p "Have you copied and pasted the public key to your GitHub account (see https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account)? (yes/no): " confirmation

# Check user confirmation
if [[ $confirmation =~ ^([yY][eE][sS]|[yY])$  ]]; then
    echo "Continuing execution..."
else
    echo "Please copy and paste the public key to your GitHub account before proceeding."
    exit 1
fi

ansible-playbook -i ./hosts ./gen_config.yaml