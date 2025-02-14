import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from web3 import Web3

print("Available environment variables:", os.environ)  # Print all available env variables
print("PRIVATE_KEY:", os.getenv("PRIVATE_KEY"))
print("TOKEN_ADDRESS:", os.getenv("TOKEN_ADDRESS"))

# Load environment variables
RPC_URL = os.getenv("RPC_URL", "https://bsc-dataseed.binance.org/")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")  # Wallet private key (keep secure!)
TOKEN_ADDRESS = os.getenv("TOKEN_ADDRESS")  # BEP-20 Token contract address

if not PRIVATE_KEY or not TOKEN_ADDRESS:
    raise ValueError("PRIVATE_KEY and TOKEN_ADDRESS must be set in environment variables.")

# Connect to Binance Smart Chain
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    raise ValueError("Failed to connect to BSC network.")

# Get wallet address from private key
ACCOUNT = w3.eth.account.from_key(PRIVATE_KEY)
SENDER_ADDRESS = ACCOUNT.address

# Load BEP-20 Token Contract ABI
TOKEN_ABI = json.loads("""[
    {
        "constant": true,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]""")

# Load contract
token_contract = w3.eth.contract(address=w3.to_checksum_address(TOKEN_ADDRESS), abi=TOKEN_ABI)

# FastAPI app
app = FastAPI()

class TransferRequest(BaseModel):
    recipient: str  # Wallet address to receive tokens
    amount: float   # Amount to send

@app.post("/send_tokens/")
async def send_tokens(data: TransferRequest):
    recipient_address = w3.to_checksum_address(data.recipient)
    amount_wei = int(data.amount * (10 ** 18))  # Convert to smallest unit

    # Check sender balance
    sender_balance = token_contract.functions.balanceOf(SENDER_ADDRESS).call()
    if sender_balance < amount_wei:
        raise HTTPException(status_code=400, detail="Insufficient token balance.")

    # Build transaction
    nonce = w3.eth.get_transaction_count(SENDER_ADDRESS)
    txn = token_contract.functions.transfer(recipient_address, amount_wei).build_transaction({
        'chainId': 56,  # BSC Mainnet
        'gas': 200000,
        'gasPrice': w3.to_wei('5', 'gwei'),
        'nonce': nonce,
    })

    # Sign transaction
    signed_txn = w3.eth.account.sign_transaction(txn, PRIVATE_KEY)
    
    # Send transaction
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)

    return {"status": "success", "tx_hash": tx_hash.hex()}

@app.get("/")
async def root():
    return {"message": "BSC Token Transfer API is running!"}
