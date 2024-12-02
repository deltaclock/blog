if [ "$CF_PAGES_BRANCH" == "master" ]; then
    hugo -b $CF_PAGES_URL
elif [ "$CF_PAGES_BRANCH" == "staging" ]; then
    hugo -D -b $CF_PAGES_URL
else
    echo "branch: $CF_PAGES_BRANCH"
fi