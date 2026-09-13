import { Card, CardBody, CardHeader } from "../../ui/Layout";
import { NativeTetravox } from "../../viewer/NativeTetravox";

export function TetravoxCard() {
  return <Card><CardHeader title="TetraVox" /><CardBody><NativeTetravox /></CardBody></Card>;
}
