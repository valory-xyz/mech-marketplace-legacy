# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2025 Valory AG
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""This package contains a scaffold of a handler."""
import threading
import time
from typing import Any, Dict, List, Optional, cast

from aea.protocols.base import Message
from aea.skills.base import Handler

from packages.valory.connections.ledger.connection import (
    PUBLIC_ID as LEDGER_CONNECTION_PUBLIC_ID,
)
from packages.valory.protocols.acn_data_share import AcnDataShareMessage
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.ipfs import IpfsMessage
from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.skills.task_execution.models import Params


PENDING_TASKS = "pending_tasks"
DONE_TASKS = "ready_tasks"
SUBMITTED_TASKS = "submitted_tasks"
DONE_TASKS_LOCK = "lock"
LAST_SUCCESSFUL_READ = "last_successful_read"
LAST_SUCCESSFUL_EXECUTED_TASK = "last_successful_executed_task"
WAS_LAST_READ_SUCCESSFUL = "was_last_read_successful"

LEDGER_API_ADDRESS = str(LEDGER_CONNECTION_PUBLIC_ID)


class BaseHandler(Handler):
    """Base Handler"""

    def setup(self) -> None:
        """Set up the handler."""
        self.context.logger.info(f"{self.__class__.__name__}: setup method called.")

    def cleanup_dialogues(self) -> None:
        """Clean up all dialogues."""
        for handler_name in self.context.handlers.__dict__.keys():
            dialogues_name = handler_name.replace("_handler", "_dialogues")
            dialogues = getattr(self.context, dialogues_name)
            dialogues.cleanup()

    @property
    def params(self) -> Params:
        """Get the parameters."""
        return cast(Params, self.context.params)

    def teardown(self) -> None:
        """Teardown the handler."""
        self.context.logger.info(f"{self.__class__.__name__}: teardown called.")

    def on_message_handled(self, _message: Message) -> None:
        """Callback after a message has been handled."""
        self.params.request_count += 1
        if self.params.request_count % self.params.cleanup_freq == 0:
            self.context.logger.info(
                f"{self.params.request_count} requests processed. Cleaning up dialogues."
            )
            self.cleanup_dialogues()


class AcnHandler(BaseHandler):
    """ACN API message handler."""

    SUPPORTED_PROTOCOL = AcnDataShareMessage.protocol_id

    def handle(self, message: Message) -> None:
        """Handle the message."""
        # we don't respond to ACN messages at this point
        self.context.logger.info(f"Received message: {message}")
        self.on_message_handled(message)


class IpfsHandler(BaseHandler):
    """IPFS API message handler."""

    SUPPORTED_PROTOCOL = IpfsMessage.protocol_id

    def handle(self, message: Message) -> None:
        """
        Implement the reaction to an IPFS message.

        :param message: the message
        """
        self.context.logger.info(f"Received message: {message}")
        ipfs_msg = cast(IpfsMessage, message)
        if ipfs_msg.performative == IpfsMessage.Performative.ERROR:
            self.context.logger.warning(
                f"IPFS Message performative not recognized: {ipfs_msg.performative}"
            )
            self.params.in_flight_req = False
            return

        dialogue = self.context.ipfs_dialogues.update(ipfs_msg)
        nonce = dialogue.dialogue_label.dialogue_reference[0]
        callback = self.params.req_to_callback.pop(nonce)
        deadline = self.params.req_to_deadline.pop(nonce)

        if deadline and time.time() > deadline:
            # Deadline reached
            self.context.logger.info(f"Deadline reached for task with nonce {nonce}.")
            self.params.in_flight_req = False
            self.params.is_cold_start = False
            return

        if callback is not None:
            callback(ipfs_msg, dialogue)
        self.params.in_flight_req = False
        self.params.is_cold_start = False
        self.on_message_handled(message)


class ContractHandler(BaseHandler):
    """Contract API message handler."""

    SUPPORTED_PROTOCOL = ContractApiMessage.protocol_id

    def setup(self) -> None:
        """Setup the contract handler."""
        self.context.shared_state[PENDING_TASKS] = []
        self.context.shared_state[DONE_TASKS] = []
        self.context.shared_state[SUBMITTED_TASKS] = []
        self.context.shared_state[DONE_TASKS_LOCK] = threading.Lock()
        super().setup()

    @property
    def pending_tasks(self) -> List[Dict[str, Any]]:
        """Get pending_tasks."""
        return self.context.shared_state[PENDING_TASKS]

    def set_last_successful_read(self, block_number: Optional[int]) -> None:
        """Set the last successful read."""
        self.context.shared_state[LAST_SUCCESSFUL_READ] = (block_number, time.time())

    def set_was_last_read_successful(self, was_successful: bool) -> None:
        """Set the last successful read."""
        self.context.shared_state[WAS_LAST_READ_SUCCESSFUL] = was_successful

    def handle(self, message: Message) -> None:
        """
        Implement the reaction to a contract message.

        :param message: the message
        """
        self.context.logger.info(f"Received message: {message}")
        contract_api_msg = cast(ContractApiMessage, message)
        if contract_api_msg.performative != ContractApiMessage.Performative.STATE:
            # for healthcheck metrics
            self.set_was_last_read_successful(False)
            self.context.logger.warning(
                f"Contract API Message performative not recognized: {contract_api_msg.performative}"
            )
            self.params.in_flight_req = False
            return

        body = contract_api_msg.state.body
        self._handle_get_undelivered_reqs(body)
        self.set_was_last_read_successful(True)
        self.on_message_handled(message)
        self.params.in_flight_req = False

    def _handle_get_undelivered_reqs(self, body: Dict[str, Any]) -> None:
        """Handle get undelivered reqs."""
        reqs = body.get("data", [])
        if len(reqs) == 0:
            # for healthcheck metrics
            queue_size = len(self.pending_tasks)
            self.context.logger.info(f"Number of pending tasks: {queue_size=}")
            self.set_last_successful_read(
                self.params.req_params.from_block[cast(str, self.params.req_type)]
            )
            return

        self.params.req_params.from_block[cast(str, self.params.req_type)] = (
            max([req["block_number"] for req in reqs]) + 1
        )
        self.context.logger.info(f"Received {len(reqs)} new requests.")
        # for healthcheck metrics
        self.set_last_successful_read(
            self.params.req_params.from_block[cast(str, self.params.req_type)]
        )
        current_tasks = set(
            [task["requestId"] for task in self.pending_tasks]
            + [task["request_id"] for task in self.context.shared_state[DONE_TASKS]]
            + (
                [self.params.executing_task.get("requestId")]
                if self.params.executing_task
                and self.params.executing_task.get("requestId")
                else []
            )
        )
        reqs = [
            req
            for req in reqs
            if req["block_number"] % self.params.num_agents == self.params.agent_index
            and req["requestId"] not in current_tasks
        ]
        self.context.logger.info(f"Processing only {len(reqs)} of the new requests.")
        self.pending_tasks.extend(reqs)
        self.context.logger.info(
            f"Monitoring new reqs from block {self.params.req_params.from_block[cast(str, self.params.req_type)]}"
        )
        queue_size = len(self.pending_tasks)
        self.context.logger.info(f"Number of pending tasks: {queue_size=}")


class LedgerHandler(BaseHandler):
    """Ledger API message handler."""

    SUPPORTED_PROTOCOL = LedgerApiMessage.protocol_id

    def handle(self, message: Message) -> None:
        """
        Implement the reaction to a ledger message.

        :param message: the message
        """
        self.context.logger.info(f"Received message: {message}")
        ledger_api_msg = cast(LedgerApiMessage, message)
        if ledger_api_msg.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.warning(
                f"Ledger API Message performative not recognized: {ledger_api_msg.performative}"
            )
            self.params.in_flight_req = False
            return

        block_number = ledger_api_msg.state.body["number"]
        self.params.req_params.from_block[cast(str, self.params.req_type)] = (
            block_number - self.params.from_block_range
        )
        self.params.in_flight_req = False
        self.on_message_handled(message)
