import { useEffect } from "react";
import { Outlet } from "react-router-dom";
import { useSseStore } from "../store/sseStore";

export default function PrivateLayout() {
  const connect = useSseStore((state) => state.connect);

  const disconnect = useSseStore((state) => state.disconnect);

  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
  }, []);

  return <Outlet />;
}
