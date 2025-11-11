param(
  [string]$SrvHost="0.0.0.0",
  [int]$SrvPort=5000,
  [int]$BoardSize=15,
  [int]$WinLen=5
  [switch]$EnableChat,
  [switch]$EnableRooms,
  [int]$TurnTimer=0,
  [string]$LogDir=""
)
$flags = @("--host",$SrvHost,"--port",$SrvPort,"--size",$BoardSize,"--win",$WinLen)
if ($EnableChat)  { $flags += "--enable-chat" }
if ($EnableRooms) { $flags += "--enable-rooms" }
if ($TurnTimer -gt 0) { $flags += @("--turn-timer",$TurnTimer) }
if ($LogDir -ne "")   { $flags += @("--log-dir",$LogDir) }
python server.py $flags --host $SrvHost --port $SrvPort --size $BoardSize --win $WinLen

