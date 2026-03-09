import { motion } from 'motion/react';
import { BrainCircuit, Database, TrendingUp, ChevronRight, Activity } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useEffect, useState } from 'react';

const StatPill = ({ prefix = "", num, suffix, label, isFloat = false }: {
  prefix?: string;
  num: number;
  suffix: string;
  label: string;
  isFloat?: boolean;
}) => {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let start = 0;
    const duration = 1500;
    const steps = 60;
    const increment = num / steps;
    let currentStep = 0;

    const timer = setInterval(() => {
      currentStep++;
      start += increment;
      if (currentStep >= steps) {
        setCount(num);
        clearInterval(timer);
      } else {
        setCount(start);
      }
    }, duration / steps);

    return () => clearInterval(timer);
  }, [num]);

  const displayNum = isFloat ? count.toFixed(2) : Math.floor(count);

  return (
    <div className="flex items-center gap-2 bg-[#1E2A3A] border border-[#2D3F55] px-4 py-2 rounded-full text-sm text-[#94A3B8] shadow-sm">
      <div className="w-1.5 h-1.5 rounded-full bg-[#E8531A]" />
      <span>{prefix}<span className="font-bold text-white">{displayNum}{suffix}</span> {label}</span>
    </div>
  );
};

const PlayerCard = ({
  player,
  team,
  stat,
  label,
  image,
  className,
}: {
  player: string;
  team: string;
  stat: string;
  label: string;
  image: string;
  className: string;
}) => (
  <div className={`absolute top-1/2 left-1/2 w-72 bg-[#1E2A3A] border border-[#2D3F55] rounded-2xl shadow-2xl flex flex-col overflow-hidden transition-all duration-500 ease-out group/card ${className}`}>
    <div className="p-6 flex flex-col items-center relative">
      <div className="w-24 h-24 rounded-full overflow-hidden mb-4 border-2 border-[#2D3F55] bg-[#0F1624] relative">
        <img
          src={image}
          alt={player}
          referrerPolicy="no-referrer"
          className="object-cover object-top w-full h-full"
        />
      </div>
      <h3 className="text-xl font-bold text-white">{player}</h3>
      <p className="text-[#94A3B8] text-xs uppercase tracking-widest mt-1">
        {team}
      </p>
    </div>

    <div className="px-6 py-5 bg-[#0F1624]/50 flex flex-col items-center justify-center border-y border-[#2D3F55]">
      <div className="text-[48px] leading-none font-bold text-[#E8531A]">{stat}</div>
      <div className="text-[#94A3B8] text-sm mt-2 font-medium uppercase tracking-wider">{label}</div>
    </div>

    <div className="flex w-full h-14">
      <button className="flex-1 flex items-center justify-center border-r border-[#2D3F55] text-[#EF4444] font-semibold tracking-wider hover:bg-[#EF4444]/10 transition-colors">
        LESS
      </button>
      <button className="flex-1 flex items-center justify-center bg-[#22C55E] text-[#0F1624] font-bold tracking-wider hover:bg-[#1ea850] transition-colors">
        MORE
      </button>
    </div>
  </div>
);

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0F1624] text-white font-sans selection:bg-[#E8531A]/30">
      {/* Navigation */}
      <nav className="fixed top-0 w-full z-50 border-b border-[#2D3F55]/50 bg-[#0F1624]/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-6 h-6 text-[#E8531A]" />
            <span className="text-xl font-bold tracking-tight">Chalk</span>
          </div>
          <Link
            to="/dashboard"
            className="text-sm font-medium text-[#94A3B8] hover:text-white transition-colors"
          >
            Sign In
          </Link>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 lg:pt-48 lg:pb-32 overflow-hidden">
        <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-16 items-center">

          {/* Left Content */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="max-w-2xl"
          >
            <div className="flex items-center gap-3 mb-8">
              <div className="flex items-center gap-2 bg-[#22C55E]/10 px-3 py-1 rounded-full border border-[#22C55E]/20">
                <div className="w-2 h-2 rounded-full bg-[#22C55E] animate-pulse" />
                <span className="text-xs font-bold tracking-widest text-[#22C55E]">LIVE</span>
              </div>
              <span className="text-xs font-bold tracking-widest text-[#94A3B8]">NBA PREDICTIONS</span>
            </div>

            <h1 className="text-4xl sm:text-5xl lg:text-[64px] font-bold leading-[1.1] tracking-tight mb-6">
              Stop Guessing.<br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#E8531A] to-[#ff7a45]">Start Chalking.</span>
            </h1>

            <p className="text-xl text-[#94A3B8] mb-10 leading-relaxed max-w-xl">
              AI-powered player projections with Vegas-beating accuracy. Know the edge before the lines move.
            </p>

            <div className="flex flex-col sm:flex-row gap-4 mb-12">
              <Link
                to="/dashboard"
                className="inline-flex items-center justify-center gap-2 bg-[#E8531A] hover:bg-[#d44815] text-white px-8 py-4 rounded-xl font-semibold transition-all hover:scale-[1.02] hover:shadow-[0_0_30px_rgba(232,83,26,0.3)]"
              >
                View Tonight&apos;s Slate
                <ChevronRight className="w-5 h-5" />
              </Link>
              <button className="inline-flex items-center justify-center gap-2 border border-[#2D3F55] hover:border-[#94A3B8] hover:bg-[#1E2A3A]/50 text-white px-8 py-4 rounded-xl font-semibold transition-all">
                See How It Works
              </button>
            </div>

            <div className="flex flex-wrap gap-3">
              <StatPill num={4.94} suffix=" pts MAE" label="· Vegas-competitive accuracy" isFloat={true} />
              <StatPill num={159} suffix=" tests" label="· 0 failures" />
              <StatPill prefix="p99 = " num={40} suffix="ms" label="· Real-time predictions" />
            </div>
          </motion.div>

          {/* Right Content - Interactive Cards */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="relative h-[600px] w-full hidden lg:flex items-center justify-center group perspective-[2000px]"
          >
            {/* Card 3 (Back) */}
            <PlayerCard
              player="Tyrese Haliburton"
              team="IND"
              stat="9.8"
              label="Assists"
              image="https://cdn.nba.com/headshots/nba/latest/1040x760/1630169.png"
              className="z-10 -translate-x-[calc(50%-60px)] -translate-y-[calc(50%-60px)] rotate-[8deg] scale-[0.85] opacity-60 group-hover:-translate-x-[calc(50%-140px)] group-hover:-translate-y-1/2 group-hover:rotate-[12deg] group-hover:scale-100 group-hover:opacity-100 hover:!translate-y-[calc(-50%-16px)] hover:!z-50 hover:!shadow-[0_20px_40px_rgba(0,0,0,0.5)]"
            />
            {/* Card 2 (Middle) */}
            <PlayerCard
              player="Nikola Jokic"
              team="DEN"
              stat="11.2"
              label="Rebounds"
              image="https://cdn.nba.com/headshots/nba/latest/1040x760/203999.png"
              className="z-20 -translate-x-[calc(50%-30px)] -translate-y-[calc(50%-30px)] rotate-[4deg] scale-[0.92] opacity-80 group-hover:-translate-x-1/2 group-hover:-translate-y-1/2 group-hover:rotate-0 group-hover:scale-100 group-hover:opacity-100 hover:!translate-y-[calc(-50%-16px)] hover:!z-50 hover:!shadow-[0_20px_40px_rgba(0,0,0,0.5)]"
            />
            {/* Card 1 (Front) */}
            <PlayerCard
              player="Jayson Tatum"
              team="BOS"
              stat="24.5"
              label="Points"
              image="https://cdn.nba.com/headshots/nba/latest/1040x760/1628369.png"
              className="z-30 -translate-x-1/2 -translate-y-1/2 rotate-0 scale-100 opacity-100 group-hover:-translate-x-[calc(50%+140px)] group-hover:-translate-y-1/2 group-hover:-rotate-[12deg] group-hover:scale-100 hover:!translate-y-[calc(-50%-16px)] hover:!z-50 hover:!shadow-[0_20px_40px_rgba(0,0,0,0.5)] shadow-[0_10px_30px_rgba(0,0,0,0.4)]"
            />
          </motion.div>
        </div>
      </section>

      {/* Social Proof Bar */}
      <div className="w-full bg-[#0B101A] border-y border-[#2D3F55]/50 py-4 overflow-x-auto">
        <div className="max-w-7xl mx-auto px-6 flex items-center justify-center text-sm font-medium text-[#94A3B8] tracking-wide">
          <div className="flex items-center gap-4 md:gap-6 whitespace-nowrap">
            <span>527 players tracked</span>
            <span className="w-1.5 h-1.5 rounded-full bg-[#2D3F55]" />
            <span>12,927 games analyzed</span>
            <span className="w-1.5 h-1.5 rounded-full bg-[#2D3F55]" />
            <span>147,000+ predictions logged</span>
            <span className="w-1.5 h-1.5 rounded-full bg-[#2D3F55]" />
            <span>40ms avg response time</span>
            <span className="w-1.5 h-1.5 rounded-full bg-[#2D3F55]" />
            <span className="text-[#22C55E]">MAE beating Vegas on 4/4 stats</span>
          </div>
        </div>
      </div>

      {/* How It Works */}
      <section className="py-32 relative">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-20">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">The Edge is in the Math</h2>
            <p className="text-[#94A3B8] max-w-2xl mx-auto text-lg">
              We don&apos;t rely on gut feelings. Our models process millions of data points to find discrepancies in the betting lines.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: 0.1 }}
              className="bg-[#1E2A3A]/50 border border-[#2D3F55] p-8 rounded-2xl hover:bg-[#1E2A3A] transition-colors"
            >
              <div className="w-14 h-14 bg-[#0F1624] border border-[#2D3F55] rounded-xl flex items-center justify-center mb-6 text-[#E8531A]">
                <Database className="w-7 h-7" />
              </div>
              <h3 className="text-xl font-bold mb-3">We Crunch the Data</h3>
              <p className="text-[#94A3B8] leading-relaxed">
                Rolling averages, opponent defense, injury context, and 74 distinct features per player updated in real-time.
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: 0.2 }}
              className="bg-[#1E2A3A]/50 border border-[#2D3F55] p-8 rounded-2xl hover:bg-[#1E2A3A] transition-colors"
            >
              <div className="w-14 h-14 bg-[#0F1624] border border-[#2D3F55] rounded-xl flex items-center justify-center mb-6 text-[#E8531A]">
                <BrainCircuit className="w-7 h-7" />
              </div>
              <h3 className="text-xl font-bold mb-3">Models Find the Edge</h3>
              <p className="text-[#94A3B8] leading-relaxed">
                XGBoost trained on 5 seasons of historical data, utilizing strict walk-forward validation to ensure zero data leakage.
              </p>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: 0.3 }}
              className="bg-[#1E2A3A]/50 border border-[#2D3F55] p-8 rounded-2xl hover:bg-[#1E2A3A] transition-colors"
            >
              <div className="w-14 h-14 bg-[#0F1624] border border-[#2D3F55] rounded-xl flex items-center justify-center mb-6 text-[#E8531A]">
                <TrendingUp className="w-7 h-7" />
              </div>
              <h3 className="text-xl font-bold mb-3">You See the Edge</h3>
              <p className="text-[#94A3B8] leading-relaxed">
                Clear confidence intervals, O/U probabilities, and fantasy value projections, all presented in one actionable dashboard.
              </p>
            </motion.div>
          </div>
        </div>
      </section>

      {/* Dashboard Preview */}
      <section className="py-20 relative overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-[#E8531A]/20 blur-[120px] rounded-full pointer-events-none" />

        <div className="max-w-6xl mx-auto px-6 relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.7 }}
            className="rounded-2xl border border-[#2D3F55] bg-[#0F1624] shadow-[0_0_60px_rgba(232,83,26,0.15)] overflow-hidden"
          >
            {/* Browser Chrome */}
            <div className="h-12 bg-[#1E2A3A] border-b border-[#2D3F55] flex items-center px-4 gap-2">
              <div className="w-3 h-3 rounded-full bg-[#EF4444]" />
              <div className="w-3 h-3 rounded-full bg-[#F59E0B]" />
              <div className="w-3 h-3 rounded-full bg-[#22C55E]" />
              <div className="ml-4 bg-[#0F1624] border border-[#2D3F55] rounded-md px-4 py-1 text-xs text-[#94A3B8] flex-1 max-w-sm flex items-center gap-2">
                <Activity className="w-3 h-3" /> chalk.app/dashboard
              </div>
            </div>

            {/* Mockup Content */}
            <div className="p-8 grid grid-cols-1 md:grid-cols-4 gap-6 bg-[#0F1624]">
              {/* Sidebar */}
              <div className="hidden md:flex flex-col gap-4 border-r border-[#2D3F55] pr-6">
                <div className="h-8 bg-[#1E2A3A] rounded-md w-3/4 mb-4" />
                <div className="h-4 bg-[#1E2A3A] rounded-md w-full" />
                <div className="h-4 bg-[#1E2A3A] rounded-md w-5/6" />
                <div className="h-4 bg-[#1E2A3A] rounded-md w-full" />
                <div className="h-4 bg-[#1E2A3A] rounded-md w-4/5" />
              </div>

              {/* Main Content */}
              <div className="md:col-span-3 flex flex-col gap-6">
                <div className="flex justify-between items-center">
                  <div className="h-8 bg-[#1E2A3A] rounded-md w-48" />
                  <div className="h-8 bg-[#1E2A3A] rounded-md w-32" />
                </div>
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                  {[1, 2, 3, 4, 5, 6].map((i) => (
                    <div key={i} className="bg-[#1E2A3A] border border-[#2D3F55] rounded-xl p-4 flex flex-col gap-3">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-[#2D3F55]" />
                        <div className="flex-1">
                          <div className="h-3 bg-[#2D3F55] rounded-md w-24 mb-2" />
                          <div className="h-2 bg-[#2D3F55] rounded-md w-16" />
                        </div>
                      </div>
                      <div className="h-12 bg-[#0F1624] rounded-md mt-2 flex items-center justify-center">
                        <div className="h-6 bg-[#E8531A]/20 rounded-md w-1/2" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>

          <div className="text-center mt-16">
            <h3 className="text-2xl font-bold mb-6">See every player. Every game. Every edge.</h3>
            <Link
              to="/dashboard"
              className="inline-flex items-center justify-center gap-2 bg-[#E8531A] hover:bg-[#d44815] text-white px-8 py-4 rounded-xl font-semibold transition-all hover:scale-[1.02] hover:shadow-[0_0_30px_rgba(232,83,26,0.3)]"
            >
              Open Chalk Dashboard
            </Link>
          </div>
        </div>
      </section>

      {/* CTA Footer Banner */}
      <footer className="bg-[#0B101A] border-t border-[#2D3F55] pt-24 pb-12">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-bold mb-6">Tonight&apos;s slate is loading.</h2>
          <p className="text-xl text-[#94A3B8] mb-10">
            Get projections for every player in tonight&apos;s games — free.
          </p>
          <Link
            to="/dashboard"
            className="inline-flex items-center justify-center gap-2 bg-[#E8531A] hover:bg-[#d44815] text-white px-10 py-5 rounded-xl text-lg font-bold transition-all hover:scale-[1.02] hover:shadow-[0_0_30px_rgba(232,83,26,0.3)] mb-20"
          >
            Open Chalk Dashboard
          </Link>

          <div className="border-t border-[#2D3F55]/50 pt-8 flex flex-col items-center gap-4">
            <div className="flex items-center gap-2 text-[#94A3B8]">
              <Activity className="w-5 h-5 text-[#E8531A]" />
              <span className="font-bold tracking-tight text-white">Chalk</span>
            </div>
            <p className="text-sm text-[#64748B]">
              Powered by XGBoost · Built for bettors and fantasy players.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
