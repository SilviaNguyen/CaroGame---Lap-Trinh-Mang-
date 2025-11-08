param(
  [string]$ServerAddr="127.0.0.1",
  [int]$ServerPort=5000,
  [string]$PlayerName=("Player"+(Get-Random -Minimum 100 -Maximum 999))
)
python client_pygame.py --server $ServerAddr --port $ServerPort --name $PlayerName
