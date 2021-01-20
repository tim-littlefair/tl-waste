#!/bin/sh

export gpg_user=$1
export credentials_csv=$2
export credentials_sh=`dirname $2`/`basename $2 .csv`.sh

usage() {
    echo Usage: $0 [gpg_user_email] [aws_credentials_csv]    
}

if [ ! -r "$2" ]
then
    usage
    exit 1
elif [ "$2" -eq "$credentials_sh"]
then
    usage 
    exit 1
fi

dump() {
    echo ==== $1
    echo "$2"
    echo ----
}


unset all_vars local_vars public_vars
# Variables defined in lower case are intended for use within this script
export local_vars=`env | grep ^aws_ | cut -f1 -d= `
# Variables defined in upper case are intended for use in the generated script
export public_vars=`env | grep ^AWS_ | cut -f1 -d=`

export all_vars=`echo $local_vars $public_vars | sort | uniq | paste -d' ' -`
dump all_vars "$all_vars"
unset public_vars local_vars

credentials_line=`cat $credentials_csv | head -2 | tail -1`
echo $credentials_line
export aws_web_username=`echo $credentials_line | cut -f 1 -d, -`
export aws_web_password=`echo $credentials_line | cut -f 2 -d, - | sed -e s/\|/\\|/ -e s/\n//`
export aws_api_keyid=`echo $credentials_line | cut -f 3 -d, -`
export aws_api_secretkey=`echo $credentials_line | cut -f 4 -d, -`
export aws_web_url=`echo -n $credentials_line | cut -f 5 -d, - | tr -d '\n' `

export aws_browser_path=~/aws_bin/browser.sh

export plaintext_env="
echo '$aws_web_password' | pbcopy - ; \
export AWS_BROWSER_PATH=$aws_browser_path ; \
export AWS_DEFAULT_REGION=ap-southeast-2 ; \
export AWS_ACCESS_KEY_ID=$aws_api_keyid ; \
export AWS_SECRET_ACCESS_KEY=$aws_api_secretkey ; \
env | grep ^AWS_ ; \
sh $aws_browser_path $aws_web_url ; \
"

dump plaintext_env "$plaintext_env" 

export encrypted_env=`echo $plaintext_env | gpg2 -e -r $gpg_user - | base64`

dump encrypted_env "$encrypted_env"

cat > $credentials_sh <<+ 
#!/bin/sh

unset $all_vars

export gpg_user=$gpg_user
eval \`echo -n $encrypted_env | base64 -d | gpg2 -d -r $gpg_user\` > /dev/null

+

echo Generated script is in $credentials_sh
# dump $credentials_sh `cat $credentials_sh`

source $credentials_sh

