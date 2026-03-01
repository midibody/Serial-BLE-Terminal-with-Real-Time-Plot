// BLE Library for Seeed board, with initBLE, readBLE, writeBLE

#if USE_BLE==1

#include <bluefruit.h>
#define S_MAX_BLE_RX  500

#define S_MAX_BLE_WRITE 240 // not sure the exact MTU limit

char aInput[S_MAX_BLE_RX];
BLEUart bleuart;

bool fBleConnected = false;

//*******************************
void initBLE(const char * pName)
{

Bluefruit.configPrphBandwidth(BANDWIDTH_MAX);

Bluefruit.begin();
Bluefruit.setName(pName);

// Conn params (OK)
Bluefruit.Periph.setConnInterval(6, 12);
Bluefruit.Periph.setConnSupervisionTimeout(400);

bleuart.begin();

// Advertising payload
Bluefruit.Advertising.clearData();
Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
Bluefruit.Advertising.addTxPower();
Bluefruit.Advertising.addService(bleuart);
Bluefruit.Advertising.addName();

// Scan response (to ensure the name is visible)
Bluefruit.ScanResponse.clearData();
Bluefruit.ScanResponse.addName();

Bluefruit.Advertising.setFastTimeout(0);   // to avoid to switch to slow advertising after 30 seconds
Bluefruit.Advertising.start(0);

  /* Previous init 
  // Doit être AVANT begin()
  Bluefruit.configPrphBandwidth(BANDWIDTH_MAX);  
  //Bluefruit.autoConnLed(false); // to disable the blue led blich while advertising
  Bluefruit.begin();
  Bluefruit.setName(pName);
  
  //Bluefruit.configPrphConn(6, 12, 0, 400);        // optionnel: min/max interval (7.5ms..15ms), latency, timeout

  //Bluefruit.Periph.setConnInterval(6, 12);
  //Bluefruit.Periph.setConnSupervisionTimeout(400); // 4s → 400 * 10ms

  bleuart.begin();
  Bluefruit.Advertising.addService(bleuart);
  Bluefruit.Advertising.addName();//??
  Bluefruit.Advertising.start(0);
  */
}

void disconnect_callback(uint16_t conn_handle, uint8_t reason)
{
  Bluefruit.Advertising.start(0);
}

//**********************
bool isBLEConnected()
{

  // "session BLE valide" = connecté + notifications activées
  fBleConnected = Bluefruit.connected() && bleuart.notifyEnabled();

  //sprintf (aDebug, "BLE connected=%d, BLE NotifyEnabled=%d",Bluefruit.connected() , bleuart.notifyEnabled());
  //serialPrintln(aDebug);

  return fBleConnected;
}

//**************************
uint16_t readBLE(char *pRet, uint32_t sMaxInput)
{
 uint8_t idx = 0;
  char c;

if (sMaxInput> S_MAX_BLE_RX -1) sMaxInput = S_MAX_BLE_RX -1;

  aInput[0] = 0;

  while (bleuart.available() ) 
    {
      c = bleuart.read();
      serialPrint(c);

      // Fin de ligne → chaîne terminée
      if (c == '\n' || c == '\r') {
        if (idx > 0) {
          aInput[idx] = '\0'; 
        }
      }
      else {
      
        if (idx < sMaxInput - 1) {
          aInput[idx++] = c;
        }
        
      }
  }
aInput[idx]= 0;
strcpy(pRet, aInput);
return idx;
}

//**********************************
void writeBLE(const char* p)
{
if (!fBleConnected) return;

   size_t len = strlen(p);
  size_t off = 0;
  size_t sBloc;

  while (off < len)
  {
    sBloc = (len - off < S_MAX_BLE_WRITE)? len-off : S_MAX_BLE_WRITE;

    size_t n = bleuart.write(p + off, sBloc);
    if (n == 0)
    {
      // buffer plein -> laisse le temps à la pile d’émettre
      delay(1);
      
      continue;
    }
    off += sBloc;
  }
}

//***************************
void writeBLEln(const char *pData) {
  writeBLE(pData);
  writeBLE("\n");

}

#else // USE_BLE = false

//***************************
void writeBLE(const char *pData)
{
}
#endif

