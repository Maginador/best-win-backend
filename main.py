import os
import json
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from web3 import Web3

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
RPC_URL = os.getenv("RPC_URL", "https://bsc-dataseed.binance.org/")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")  # Wallet private key (keep secure!)
TOKEN_ADDRESS = os.getenv("TOKEN_ADDRESS")  # BEP-20 Token contract address

if not PRIVATE_KEY or not TOKEN_ADDRESS:
    logger.error("PRIVATE_KEY and TOKEN_ADDRESS must be set in environment variables.")
    raise ValueError("PRIVATE_KEY and TOKEN_ADDRESS must be set in environment variables.")

# Connect to Binance Smart Chain
logger.info(f"Connecting to BSC network via RPC: {RPC_URL}")
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    logger.error("Failed to connect to BSC network.")
    raise ValueError("Failed to connect to BSC network.")
else:
    logger.info("Successfully connected to BSC network.")

# Get wallet address from private key
ACCOUNT = w3.eth.account.from_key(PRIVATE_KEY)
SENDER_ADDRESS = ACCOUNT.address
logger.info(f"Using sender address: {SENDER_ADDRESS}")

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
logger.info(f"Loaded contract at address: {TOKEN_ADDRESS}")

# FastAPI app
app = FastAPI()

class TransferRequest(BaseModel):
    recipient: str  # Wallet address to receive tokens
    amount: float   # Amount to send

@app.post("/send_tokens/")
async def send_tokens(data: TransferRequest):
    try:
        logger.info(f"Received request to send {data.amount} tokens to {data.recipient}")
        
        recipient_address = w3.to_checksum_address(data.recipient)
        amount_wei = int(data.amount * (10 ** 18))  # Convert to smallest unit

        # Check sender balance
        logger.info(f"Checking sender balance for address {SENDER_ADDRESS}")
        sender_balance = token_contract.functions.balanceOf(SENDER_ADDRESS).call()
        logger.info(f"Sender balance: {sender_balance} tokens")

        if sender_balance < amount_wei:
            logger.warning(f"Insufficient balance: {sender_balance} < {amount_wei}")
            raise HTTPException(status_code=400, detail="Insufficient token balance.")

        # Build transaction
        logger.info("Building transaction...")
        nonce = w3.eth.get_transaction_count(SENDER_ADDRESS)
        txn = token_contract.functions.transfer(recipient_address, amount_wei).build_transaction({
            'chainId': 56,  # BSC Mainnet
            'gas': 200000,
            'gasPrice': w3.to_wei('5', 'gwei'),
            'nonce': nonce,
        })
        logger.info(f"Transaction built with nonce: {nonce}")

        # Sign transaction
        logger.info("Signing transaction...")
        signed_txn = w3.eth.account.sign_transaction(txn, PRIVATE_KEY)
        logger.info("Transaction signed successfully.")

        # Send transaction
        logger.info("Sending transaction...")
        tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        logger.info(f"Transaction sent successfully, hash: {tx_hash.hex()}")
        return {"status": "success", "tx_hash": tx_hash.hex()}
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error.")

@app.get("/")
async def root():
    logger.info("Root endpoint hit.")
    return {"message": "BSC Token Transfer API is running!"}

@app.get("/health")
async def health_check():
    try:
        if w3.is_connected():
            return {"status": "healthy", "rpc_connected": True}
        else:
            return {"status": "unhealthy", "rpc_connected": False}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

# Run the app
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))  # Use Railway's PORT or default to 8000
    uvicorn.run(app, host="0.0.0.0", port=port)