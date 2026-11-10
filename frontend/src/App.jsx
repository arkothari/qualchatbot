import { Link, NavLink, Route, Routes } from "react-router-dom";
import ClientSelect from "./pages/ClientSelect.jsx";
import Chat from "./pages/Chat.jsx";
import Admin from "./pages/Admin.jsx";

const on = ({ isActive }) => (isActive ? "on" : "");

export default function App() {
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">Escalent <b>Qual Chat</b></Link>
        <nav>
          <NavLink to="/" end className={on}>Clients</NavLink>
          <NavLink to="/admin" className={on}>Admin</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<ClientSelect />} />
          <Route path="/c/:clientId" element={<Chat />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </main>
    </>
  );
}
