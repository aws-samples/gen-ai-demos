GEN_AI_CODE_SAMPLE_ZIP="gen-ai-code.zip"
if [ ! -z "$1" ]; then
 GEN_AI_CODE_SAMPLE_ZIP=$1
fi
rm ${GEN_AI_CODE_SAMPLE_ZIP}
zip -r ${GEN_AI_CODE_SAMPLE_ZIP} \
                    *.py \
                    *.txt \
                    Dockerfile \
                    pages \
                    utils \
                    lambda-srcs \
                    lex-srcs \
                    cloudformation 
