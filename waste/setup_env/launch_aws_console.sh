browser_name="Brave Browser"
browser_path="/Applications/$browser_name.app/Contents/MacOS/$browser_name"

credentials_line=`cat $1 | head -2 | tail -1`
echo $credentials_line
username=`echo $credentials_line | cut -f 1 -d, -`
password=`echo $credentials_line | cut -f 2 -d, -`
url=`echo $credentials_line | cut -f 5 -d, -`
echo "$password" | pbcopy
echo $url
nohup "$browser_path" $url &
