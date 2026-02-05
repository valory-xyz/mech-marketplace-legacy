# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2026 Valory AG
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

"""This module contains the component implementation of the `StakingToken` contract."""

from aea.common import JSONLike
from aea.configurations.base import PublicId
from aea.contracts.base import Contract
from aea.crypto.base import LedgerApi


class StakingTokenContract(Contract):
    """The Staking Token contract."""

    contract_id = PublicId.from_str("valory/staking_token:0.1.0")

    @classmethod
    def get_service_staking_state(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        service_id: int,
    ) -> JSONLike:
        """Check whether the service is staked."""
        contract_instance = cls.get_instance(ledger_api, contract_address)
        state = contract_instance.functions.getStakingState(service_id).call()
        return {"state": state}

    @classmethod
    def get_service_owner(
        cls,
        ledger_api: LedgerApi,
        contract_address: str,
        service_id: int,
    ) -> JSONLike:
        """Check whether the service is staked."""
        contract_instance = cls.get_instance(ledger_api, contract_address)
        info = contract_instance.functions.mapServiceInfo(service_id).call()
        return {"owner": info["owner"]}
