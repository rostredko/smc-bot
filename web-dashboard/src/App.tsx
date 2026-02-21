import { BacktestProvider } from "./app/providers/BacktestProvider";
import DashboardPage from "./pages/dashboard/ui/DashboardPage";

export default function App() {
  return (
    <BacktestProvider>
      <DashboardPage />
    </BacktestProvider>
  );
}