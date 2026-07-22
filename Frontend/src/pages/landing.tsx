import { useState } from "react";
import StarfieldBackground from "../components/landing/StarfieldBackground";
import { SpaceScene } from "../scene/SpaceScene";
// import style from "../css/landing/Landing.module.css";

export default function Landing() {
  const [started, setStarted] = useState(false);

  if (started) {
    return <SpaceScene />;
  }
  return (
    <>
      <StarfieldBackground />
    </>
  );
}
