#!/bin/bash


#Assigning Token and repo
TOKEN="[MY_TOKEN]"
OWNER="OWNER"
REPO="REPO"

# Fetching URL 
URL="https://api.github.com/repos/$OWNER/$REPO"

# Getting Responce from URL
repos_json=$(curl -H "Authorization: token $TOKEN" -H "Accept: application/vnd.github+json" "$URL")





# Storing the Repo Count
repo_count=$(echo "$repos_json" | jq length)

## Creating the Batch to run at a time

batch_size=20

for ((batch_start=1; batch_start<=repo_count; batch_start+=batch_size)); do
    batch_end=$((batch_start+batch_size-1))
    if [ $batch_end -gt $repo_count ]; then
        batch_end=$repo_count
    fi

    # Print the Start and End Number of repo
    echo "Processing batch from $batch_start to $batch_end"

    # Executing the Batch for Metadata
    for ((i=batch_start; i<=batch_end; i++)); do
        repo_name=$(echo "$repos_json" | jq -r ".[$i].name")
        description=$(echo "$repos_json" | jq -r ".[$i].description")
        html_url=$(echo "$repos_json" | jq -r ".[$i].html_url")
        stargazers_count=$(echo "$repos_json" | jq ".[$i].stargazers_count")
        forks_count=$(echo "$repos_json" | jq ".[$i].forks_count")
        language=$(echo "$repos_json" | jq -r ".[$i].language")
    done
done

    


  
  



