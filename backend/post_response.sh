#!/bin/sh
user="anonymous"
question=$(echo "$1" | tr -d '\n' | tr -d '\r')
answer=$(echo "$2" | tr -d '\n' | tr -d '\r')

curl -X POST -H "Content-Type: application/json" \
-d "{\"user\":\"$user\",\"question\":\"$question\",\"answer\":\"$answer\"}" \
'https://script.google.com/macros/s/AKfycbyagTWPS4Whky_66EjweC8PXGyjj78DvTqLRlZqRTmrTJAKLOvxGotKaHFLpZAWwXJs/exec'
