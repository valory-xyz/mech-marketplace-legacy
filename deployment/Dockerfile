ARG AUTONOMY_IMAGE_VERSION="latest"
ARG AUTONOMY_IMAGE_NAME="valory/open-autonomy"
FROM valory/oar-mech:bafybeif6qrvf2lgxb7s5c54bqpwfpyhqo5b6ry6ntgi35sh4ddmm645viy

RUN rm -rf /root/agent

ARG AEA_AGENT
ARG AUTHOR
ARG EXTRA_DEPENDENCIES

RUN aea init --reset --remote --ipfs --author ${AUTHOR}

WORKDIR /root

RUN AEA_AGENT=${AEA_AGENT} EXTRA_DEPENDENCIES=${EXTRA_DEPENDENCIES} bash /root/scripts/install.sh

RUN pip uninstall -y opencv-python || echo "opencv-python not installed"
RUN pip uninstall -y opencv-python-headless || echo "opencv-python-headless not installed"

# re-install headless opencv
RUN pip install opencv-python-headless==4.10.0.84

CMD ["/root/scripts/start.sh"]

HEALTHCHECK --interval=3s --timeout=600s --retries=600 CMD netstat -ltn | grep -c 26658 > /dev/null; if [ 0 != $? ]; then exit 1; fi;
