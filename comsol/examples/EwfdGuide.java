import com.comsol.model.*;
import com.comsol.model.util.ModelUtil;
import java.util.Locale;

/**
 * Straight parallel-plate waveguide in the frequency domain.
 * The plates are the default perfect-electric walls. Two numeric ports
 * sit on the ends. The tag of each port is at least five characters.
 */
public class EwfdGuide {
    public static void main(String[] args) {
        ModelUtil.initStandalone(false);
        try {
            Model model = ModelUtil.create("EwfdGuide");
            model.param().set("a", "10[mm]");
            model.param().set("L", "40[mm]");
            model.param().set("f0", "20[GHz]");
            model.param().set("n_fill", "1");

            model.component().create("comp1", true);
            model.component("comp1").geom().create("geom1", 2);
            model.component("comp1").geom("geom1").create("r1", "Rectangle");
            model.component("comp1").geom("geom1").feature("r1").set("size", new String[] {"L", "a"});
            model.component("comp1").geom("geom1").run();

            model.component("comp1").material().create("mat1", "Common");
            model.component("comp1").material("mat1").selection().all();
            model.component("comp1").material("mat1").propertyGroup()
                    .create("RefractiveIndex", "RefractiveIndex", "Refractive_index");
            model.component("comp1").material("mat1").propertyGroup("RefractiveIndex")
                    .set("n", new String[] {"n_fill"});

            model.component("comp1").selection().create("selIn", "Box");
            model.component("comp1").selection("selIn").set("entitydim", 1);
            model.component("comp1").selection("selIn").set("xmin", "-1e-6");
            model.component("comp1").selection("selIn").set("xmax", "1e-6");
            model.component("comp1").selection("selIn").set("ymin", "-1e-6");
            model.component("comp1").selection("selIn").set("ymax", "a+1e-6");
            model.component("comp1").selection("selIn").set("condition", "inside");

            model.component("comp1").selection().create("selOut", "Box");
            model.component("comp1").selection("selOut").set("entitydim", 1);
            model.component("comp1").selection("selOut").set("xmin", "L-1e-6");
            model.component("comp1").selection("selOut").set("xmax", "L+1e-6");
            model.component("comp1").selection("selOut").set("ymin", "-1e-6");
            model.component("comp1").selection("selOut").set("ymax", "a+1e-6");
            model.component("comp1").selection("selOut").set("condition", "inside");

            model.component("comp1").physics().create("ewfd", "ElectromagneticWavesFrequencyDomain", "geom1");
            model.component("comp1").physics("ewfd").feature("wee1").set("DisplacementFieldModel", "RefractiveIndex");
            model.component("comp1").physics("ewfd").create("port1", "Port", 1);
            model.component("comp1").physics("ewfd").feature("port1").selection().named("selIn");
            model.component("comp1").physics("ewfd").feature("port1").set("PortName", "1");
            model.component("comp1").physics("ewfd").feature("port1").set("PortType", "Numeric");
            model.component("comp1").physics("ewfd").feature("port1").set("PortModeType", "TE");
            model.component("comp1").physics("ewfd").feature("port1").set("PortModeNumber", "1");
            model.component("comp1").physics("ewfd").feature("port1").set("PortExcitation", "on");
            model.component("comp1").physics("ewfd").feature("port1").set("Pin", "1[W/m]");

            model.component("comp1").physics("ewfd").create("port2", "Port", 1);
            model.component("comp1").physics("ewfd").feature("port2").selection().named("selOut");
            model.component("comp1").physics("ewfd").feature("port2").set("PortName", "2");
            model.component("comp1").physics("ewfd").feature("port2").set("PortType", "Numeric");
            model.component("comp1").physics("ewfd").feature("port2").set("PortModeType", "TE");
            model.component("comp1").physics("ewfd").feature("port2").set("PortModeNumber", "1");
            model.component("comp1").physics("ewfd").feature("port2").set("PortExcitation", "off");
            model.component("comp1").physics("ewfd").feature("port2").set("Pin", "1[W/m]");

            model.component("comp1").mesh().create("mesh1", "geom1");
            model.component("comp1").mesh("mesh1").feature("size").set("hauto", 3);
            model.component("comp1").mesh("mesh1").run();

            model.study().create("std1");
            model.study("std1").create("bma1", "BoundaryModeAnalysis");
            model.study("std1").feature("bma1").set("modeFreq", "f0");
            model.study("std1").feature("bma1").set("PortName", "1");
            model.study("std1").feature("bma1").set("neigs", "1");
            model.study("std1").feature("bma1").set("shift", "n_fill");
            model.study("std1").feature("bma1").set("shiftactive", "on");
            model.study("std1").create("bma2", "BoundaryModeAnalysis");
            model.study("std1").feature("bma2").set("modeFreq", "f0");
            model.study("std1").feature("bma2").set("PortName", "2");
            model.study("std1").feature("bma2").set("neigs", "1");
            model.study("std1").feature("bma2").set("shift", "n_fill");
            model.study("std1").feature("bma2").set("shiftactive", "on");
            model.study("std1").create("freq", "Frequency");
            model.study("std1").feature("freq").set("plist", "f0");
            model.study("std1").run();

            double s21 = global(model, "gev21", "ewfd.S21dB");
            double s11 = global(model, "gev11", "ewfd.S11dB");
            System.out.println("===RESULT===");
            System.out.printf(Locale.US, "S21_dB=%.6f%n", s21);
            System.out.printf(Locale.US, "S11_dB=%.6f%n", s11);
            model.save("EwfdGuide.mph");
        } catch (Exception e) {
            System.err.println("FATAL: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        } finally {
            ModelUtil.disconnect();
        }
    }

    private static double global(Model model, String tag, String expr) {
        model.result().numerical().create(tag, "EvalGlobal");
        model.result().numerical(tag).set("expr", new String[] {expr});
        double[][] data = model.result().numerical(tag).getReal();
        if (data.length == 0 || data[0].length == 0) {
            throw new IllegalStateException("empty " + expr);
        }
        return data[0][0];
    }
}
